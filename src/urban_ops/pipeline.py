"""Transactional ingest of one pair of official API payloads.

No generated values masquerade as station observations. Files are archived before
Silver transaction; a failed database transaction leaves forensic raw archives.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text

from .bronze import archive
from .config import Config
from .normalize import SourceDataError, iso_utc, read_envelope, normalize_information, normalize_status
from .storage import get_run, init_schema, make_engine


def utc_now():
    return datetime.now(timezone.utc)


def rebuild_gold_for_day(conn, day: str, dialect: str, refreshed_at: str):
    """Gold is sample based, not time-weighted; stale/invalid records excluded."""
    if dialect == "postgresql":
        day_expr = "CAST(collected_at AT TIME ZONE 'UTC' AS DATE)"
        select_pred = f"{day_expr} = CAST(:day AS DATE)"
        day_value = "CAST(:day AS DATE)"
    else:
        day_expr = "date(collected_at)"
        select_pred = f"{day_expr} = :day"
        day_value = ":day"
    conn.execute(text(f"DELETE FROM gold_station_daily WHERE day_utc = {day_value}"), {"day": day})
    sql = f"""
        INSERT INTO gold_station_daily (
          station_id, day_utc, total_samples, usable_samples, empty_samples,
          full_samples, avg_available_bikes, avg_available_docks, refreshed_at
        )
        SELECT station_id, {day_expr}, COUNT(*),
          SUM(CASE WHEN is_usable=1 THEN 1 ELSE 0 END),
          SUM(CASE WHEN is_usable=1 AND num_bikes_available=0 THEN 1 ELSE 0 END),
          SUM(CASE WHEN is_usable=1 AND num_docks_available=0 THEN 1 ELSE 0 END),
          AVG(CASE WHEN is_usable=1 THEN num_bikes_available ELSE NULL END),
          AVG(CASE WHEN is_usable=1 THEN num_docks_available ELSE NULL END),
          :refreshed_at
        FROM fact_station_status WHERE {select_pred}
        GROUP BY station_id, {day_expr}
    """
    conn.execute(text(sql), {"day": day, "refreshed_at": refreshed_at})


def ingest(info_bytes: bytes, status_bytes: bytes, config: Config, run_id: str | None = None,
           captured_at: datetime | None = None):
    run_id = str(run_id or uuid4())
    timestamp = captured_at or utc_now()
    if timestamp.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    timestamp = timestamp.astimezone(timezone.utc)
    started_at = timestamp.isoformat(timespec="seconds")
    engine = make_engine(config.database_url)
    init_schema(engine)

    state = get_run(engine, run_id)
    if state == "success":
        return {"run_id": run_id, "status": "already_completed", "idempotent_skip": True}
    if state is not None:
        raise ValueError(f"Existing run_id {run_id} is {state}; use a new ID after a failed attempt")

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ingestion_runs(run_id,started_at,status)
            VALUES(:run_id,:started_at,'running')
        """), {"run_id": run_id, "started_at": started_at})

    # Every source payload is preserved verbatim (bytes -> gzip); computed values
    # and quarantines are separate downstream assets.
    saved = []
    try:
        saved.append(archive(config.bronze_dir, run_id, "station_information", info_bytes, timestamp))
        saved.append(archive(config.bronze_dir, run_id, "station_status", status_bytes, timestamp))
        info_root, raw_info = read_envelope(info_bytes, "station_information")
        status_root, raw_status = read_envelope(status_bytes, "station_status")
        feed_updated = status_root["lastUpdatedOther"]
        normalized_info, info_issues = normalize_information(raw_info)
        if not normalized_info:
            raise SourceDataError("No valid station metadata")
        station_by_id = {record["station_id"]: record for record in normalized_info}
        normalized_status, status_issues, quarantined = normalize_status(
            raw_status, station_by_id, feed_updated, started_at, config.max_lag_seconds
        )
        all_issues = info_issues + status_issues
        for record in normalized_info:
            record["first_seen_at"] = started_at
            record["last_seen_at"] = started_at
        for record in normalized_status:
            record["run_id"] = run_id
        issues = [{"run_id": run_id, "station_id": sid, "issue_code": code,
                   "severity": severity, "details": details}
                  for sid, code, severity, details in all_issues]
        quarantines = [{"run_id": run_id, "station_id": sid, "reason": reason, "raw_json": raw_json}
                       for sid, reason, raw_json in quarantined]
        finished = utc_now().isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(text("""
              INSERT INTO raw_snapshots(run_id,source_name,path,sha256,bytes_uncompressed)
              VALUES(:run_id,:source_name,:path,:sha256,:bytes_uncompressed)
            """), saved)
            conn.execute(text("""
              INSERT INTO dim_stations(station_id,station_code,station_name,latitude,longitude,
                                       capacity,first_seen_at,last_seen_at)
              VALUES(:station_id,:station_code,:station_name,:lat,:lon,:capacity,:first_seen_at,:last_seen_at)
              ON CONFLICT(station_id) DO UPDATE SET
                station_code=excluded.station_code, station_name=excluded.station_name,
                latitude=excluded.latitude, longitude=excluded.longitude,
                capacity=excluded.capacity, last_seen_at=excluded.last_seen_at
            """), normalized_info)
            if normalized_status:
                conn.execute(text("""
                  INSERT INTO fact_station_status(run_id,station_id,collected_at,feed_updated_at,
                        station_reported_at,num_bikes_available,num_docks_available,
                        mechanical_bikes,electric_bikes,is_installed,is_renting,is_returning,
                        reported_lag_seconds,is_usable)
                  VALUES(:run_id,:station_id,:collected_at,:feed_updated_at,:station_reported_at,
                        :num_bikes_available,:num_docks_available,:mechanical_bikes,:electric_bikes,
                        :is_installed,:is_renting,:is_returning,:reported_lag_seconds,:is_usable)
                """), normalized_status)
            if issues:
                conn.execute(text("""
                  INSERT INTO data_quality_issues(run_id,station_id,issue_code,severity,details)
                  VALUES(:run_id,:station_id,:issue_code,:severity,:details)
                """), issues)
            if quarantines:
                conn.execute(text("""
                  INSERT INTO quarantined_records(run_id,station_id,reason,raw_json)
                  VALUES(:run_id,:station_id,:reason,:raw_json)
                """), quarantines)
            conn.execute(text("""
                UPDATE ingestion_runs SET status='success',finished_at=:finished_at,
                    info_sha256=:info_sha256,status_sha256=:status_sha256,
                    station_information_count=:info_count,station_status_count=:status_count,
                    inserted_status_count=:inserted_count,issue_count=:issue_count
                WHERE run_id=:run_id
            """), {
                "run_id": run_id, "finished_at": finished,
                "info_sha256": saved[0]["sha256"], "status_sha256": saved[1]["sha256"],
                "info_count": len(raw_info), "status_count": len(raw_status),
                "inserted_count": len(normalized_status), "issue_count": len(issues),
            })
            # Always group by UTC day explicitly; not by local system timezone.
            rebuild_gold_for_day(conn, started_at[:10], engine.dialect.name, finished)
        return {"run_id": run_id, "status": "success", "stations": len(normalized_info),
                "status_samples": len(normalized_status), "quality_issues": len(issues),
                "quarantined": len(quarantines),
                "usable_samples": sum(x["is_usable"] for x in normalized_status),
                "info_feed_updated_at": iso_utc(info_root["lastUpdatedOther"]),
                "status_feed_updated_at": iso_utc(status_root["lastUpdatedOther"])}
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(text("""
              UPDATE ingestion_runs SET status='failed',finished_at=:finished_at,error=:error
              WHERE run_id=:run_id
            """), {"run_id": run_id, "finished_at": utc_now().isoformat(timespec="seconds"),
                   "error": str(exc)[:2000]})
        raise
    finally:
        engine.dispose()
