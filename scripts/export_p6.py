"""P6 portable cockpit export from *persisted* P3 Bronze/Silver/Gold SQL facts.

No calls to the live API, inferred journeys, backfilled intervals, or fixture data.
The output is an archived observation, never a live operations feed.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from urban_ops.storage import make_engine

MAX_HISTORY = 96  # Bound the static dashboard and prevent accidental huge downloads.


def utc(value: datetime | str) -> datetime:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("An ingestion timestamp without a timezone is not admissible")
    return moment.astimezone(timezone.utc)


def iso(moment: datetime | str) -> str:
    return utc(moment).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_int(value):
    return int(value) if value is not None else None


def export(database_url: str, *, history_limit: int = MAX_HISTORY, now: datetime | None = None) -> dict:
    if not 1 <= history_limit <= MAX_HISTORY:
        raise ValueError(f"history_limit must be 1..{MAX_HISTORY}")
    generated = now or datetime.now(timezone.utc)
    engine = make_engine(database_url)
    try:
        with engine.connect() as conn:
            runs = [dict(r) for r in conn.execute(text("""
                SELECT run_id, started_at, station_status_count
                FROM ingestion_runs WHERE status = 'success'
                ORDER BY started_at DESC, run_id DESC LIMIT :limit
            """), {"limit": history_limit}).mappings()]
            if not runs:
                raise ValueError("No real successful persisted collection: refusing fake cockpit data")
            latest = runs[0]
            rows = [dict(r) for r in conn.execute(text("""
                SELECT s.station_id, s.station_code, s.station_name, s.latitude, s.longitude, s.capacity,
                       f.collected_at, f.station_reported_at, f.num_bikes_available, f.num_docks_available,
                       f.mechanical_bikes, f.electric_bikes, f.reported_lag_seconds, f.is_usable,
                       f.is_installed, f.is_renting, f.is_returning
                FROM dim_stations s
                LEFT JOIN fact_station_status f ON f.station_id=s.station_id AND f.run_id=:run
                ORDER BY s.station_id
            """), {"run": latest["run_id"]}).mappings()]
            if not rows:
                raise ValueError("Missing real station catalogue")
            if not any(r["collected_at"] is not None for r in rows):
                raise ValueError("Latest successful run has no observations")
            counts = {}
            run_ids = [r["run_id"] for r in runs]
            for record in conn.execute(text("""
                SELECT run_id, COUNT(*) AS observed,
                       SUM(CASE WHEN is_usable=1 THEN 1 ELSE 0 END) AS usable,
                       SUM(CASE WHEN is_usable=1 THEN num_bikes_available ELSE 0 END) AS bikes,
                       SUM(CASE WHEN is_usable=1 THEN num_docks_available ELSE 0 END) AS docks,
                       SUM(CASE WHEN is_usable=1 AND num_bikes_available=0 THEN 1 ELSE 0 END) AS empty
                FROM fact_station_status WHERE run_id IN (""" +
                ",".join(f":r{i}" for i in range(len(run_ids))) +
                ") GROUP BY run_id"), {f"r{i}": k for i, k in enumerate(run_ids)}).mappings():
                counts[record["run_id"]] = dict(record)
            issue_rows = conn.execute(text("""
                SELECT issue_code, COUNT(*) AS count FROM data_quality_issues
                WHERE run_id=:run GROUP BY issue_code ORDER BY count DESC, issue_code
            """), {"run": latest["run_id"]}).mappings()
            issues = [{"code": r["issue_code"], "count": int(r["count"])} for r in issue_rows]
            # Per-station facts are keyed to the exact latest successful run.
            # One station may have several issue events; never infer a one-to-one count.
            station_issue_rows = [dict(r) for r in conn.execute(text("""
                SELECT station_id, issue_code, severity
                FROM data_quality_issues WHERE run_id=:run AND station_id IS NOT NULL
                ORDER BY station_id, issue_code
            """), {"run": latest["run_id"]}).mappings()]
            station_issues = {}
            for item in station_issue_rows:
                station_issues.setdefault(str(item["station_id"]), []).append({
                    "code": str(item["issue_code"]), "severity": str(item["severity"])
                })
    finally:
        engine.dispose()

    stations = []
    for r in rows:
        usable = r["is_usable"] == 1
        present = r["collected_at"] is not None
        # 'Not observed' is not a zero-bike station.
        condition = "unknown" if not usable else "empty" if r["num_bikes_available"] == 0 else "available"
        stations.append({
            "id": str(r["station_id"]), "code": str(r["station_code"] or ""),
            "name": str(r["station_name"] or "Station sans nom"),
            "lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "capacity": int(r["capacity"]), "observed": present, "usable": usable,
            "condition": condition,
            "bikes": as_int(r["num_bikes_available"]) if usable else None,
            "docks": as_int(r["num_docks_available"]) if usable else None,
            "mechanical": as_int(r["mechanical_bikes"]) if usable else None,
            "electric": as_int(r["electric_bikes"]) if usable else None,
            "reported_at": iso(r["station_reported_at"]) if r["station_reported_at"] else None,
            "lag_seconds": as_int(r["reported_lag_seconds"]),
            "is_operational": (None if not present or any(r[flag] is None for flag in ("is_installed", "is_renting", "is_returning"))
                               else all(r[flag] == 1 for flag in ("is_installed", "is_renting", "is_returning"))),
            "issues": station_issues.get(str(r["station_id"]), []),
        })
    current = counts.get(latest["run_id"])
    if not current:
        raise ValueError("No station observation in latest capture")
    history = []
    prev = None
    for run in reversed(runs):
        fact = counts.get(run["run_id"])
        if fact is None:
            continue
        at = iso(run["started_at"])
        delta = round((utc(at) - utc(prev)).total_seconds() / 60, 2) if prev else None
        history.append({
            "at": at, "observed": int(fact["observed"]),
            "usable": int(fact["usable"] or 0),
            "bikes": int(fact["bikes"] or 0) if int(fact["usable"] or 0)>0 else None,
            "docks": int(fact["docks"] or 0) if int(fact["usable"] or 0)>0 else None,
            "empty": int(fact["empty"] or 0) if int(fact["usable"] or 0)>0 else None,
            "gap_minutes": delta, "connected_to_previous": delta is not None and 0 < delta <= 20,
        })
        prev = at
    observed = int(current["observed"])
    usable = int(current["usable"] or 0)
    # Reasons can overlap. Count disjoint observation states separately.
    not_observed = sum(not s["observed"] for s in stations)
    unusable_observed = sum(s["observed"] and not s["usable"] for s in stations)
    non_operational = sum(s["observed"] and s["is_operational"] is False for s in stations)
    multiple_issues = sum(len(s["issues"]) > 1 for s in stations)
    return {
        "schema_version": 1, "dataset_type": "archived_p3_observations",
        "source": "Vélib' Métropole open data (ODbL) via URBAN-OPS P3",
        "source_url": "https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole",
        "generated_at": iso(generated), "captured_at": iso(latest["started_at"]),
        "run_id": latest["run_id"],
        "history_note": "Up to 96 archived captures; gaps are not interpolated.",
        "metrics": {"stations": len(stations), "observed": observed, "usable": usable,
                    "unusable": observed - usable, "bikes": int(current["bikes"] or 0) if usable>0 else None,
                    "docks": int(current["docks"] or 0) if usable>0 else None,
                    "empty": int(current["empty"] or 0) if usable>0 else None,
                    "capture_count": len(history)},
        "capture_quality": {"status": "no_usable_stations" if usable == 0 else "usable",
                            "message": "Aucune station avec données utilisables dans cette capture" if usable == 0 else None},
        "stations": stations, "history": history, "issues": issues,
        "quality_diagnostics": {
            "not_observed": not_observed,
            "observed_but_unusable": unusable_observed,
            "observed_non_operational": non_operational,
            "stations_with_multiple_issue_events": multiple_issues,
            "limitation": "Issue events overlap; an issue count is not a distinct station count.",
        },
        "p5_readiness": {"status": "unavailable",
                         "reason": "No release-wide P5 inventory included in this export."},
        "forecast": {"status": "unavailable", "horizon_minutes": 30,
                     "reason": "P5 has not passed real historical holdout validation."},
        "limitations": ["Captured archive, not real-time availability", "No invented trips or durations",
                         "No interpolated missing collections", "Forecast is unavailable until P5 is validated"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate a P6 cockpit snapshot from verified P3 SQL captures")
    p.add_argument("--db-url", default="sqlite:///./data/p6-real.sqlite")
    p.add_argument("--output", type=Path, default=Path("web/data/network.json"))
    p.add_argument("--history-limit", type=int, default=MAX_HISTORY)
    p.add_argument("--p5-inventory", type=Path,
                   help="Independent GitHub Release asset inventory from scripts.p5_inventory")
    args = p.parse_args(argv)
    result = export(args.db_url, history_limit=args.history_limit)
    if args.p5_inventory:
        inventory = json.loads(args.p5_inventory.read_text(encoding="utf-8"))
        gate = inventory.get("readiness")
        if not isinstance(gate, dict) or not isinstance(gate.get("ready"), bool) or \
                not isinstance(gate.get("captures"), int) or \
                inventory.get("source") != "GitHub Release asset names (not P3 revalidated content)":
            raise ValueError("Unverified P5 inventory: refusing readiness injection")
        result["p5_readiness"] = {
            "status": "eligible_to_attempt_training" if gate["ready"] else "insufficient_history",
            "checked_at_utc": iso(datetime.now(timezone.utc)),
            "captures": gate["captures"], "span_days": gate.get("span_days"),
            "coverage_estimate": gate.get("coverage_estimate"),
            "thresholds": {"min_days": 7, "min_captures": 900, "min_coverage": 0.40},
            "reason": gate.get("reason"),
            "from_utc": gate.get("from_utc"), "through_utc": gate.get("through_utc"),
            "source": inventory["source"],
            "limitation": "Release asset filename inventory, NOT checksum replay or validated +30min target pairs. Ready means permission to attempt P5 only.",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({"output": str(args.output), "capture": result["captured_at"],
                      "stations": result["metrics"]["stations"],
                      "collections": result["metrics"]["capture_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()