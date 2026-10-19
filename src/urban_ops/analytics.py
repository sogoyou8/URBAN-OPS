"""P4 analytics marts and portable, documented Power BI CSV exports.

Every numerical value is derived from persisted station snapshots; there is no
inferred journey count, exposure duration, or interpolation of missing captures.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .storage import make_engine

PARIS = ZoneInfo("Europe/Paris")


def as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("An ingestion timestamp is missing its timezone")
    return dt.astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def hour_start(dt: datetime) -> datetime:
    t = as_utc(dt)
    return t.replace(minute=0, second=0, microsecond=0)


def sample_from_row(row):
    """Status is valid only where P3 marked it usable; never coerce NULL to zero."""
    d = dict(row)
    valid = d["is_usable"] == 1
    return {
        "valid": valid,
        "empty": valid and d["num_bikes_available"] == 0,
        "full": valid and d["num_docks_available"] == 0,
        "bikes": d["num_bikes_available"] if valid else None,
        "docks": d["num_docks_available"] if valid else None,
        "mechanical": d["mechanical_bikes"] if valid else None,
        "electric": d["electric_bikes"] if valid else None,
        "lag": d["reported_lag_seconds"] if valid else None,
    }


@dataclass
class Bucket:
    samples: int = 0
    usable: int = 0
    empty: int = 0
    full: int = 0
    bikes_sum: int = 0
    docks_sum: int = 0
    mechanical_sum: int = 0
    electric_sum: int = 0
    lag_sum: int = 0
    # Captures whose status station timestamp is unchanged are distinguishable
    # from genuinely new station reports; neither equals trips.
    reported_stamps: set[str] = field(default_factory=set)

    def add(self, raw):
        v = sample_from_row(raw)
        self.samples += 1
        if v["valid"]:
            self.usable += 1
            self.empty += int(v["empty"])
            self.full += int(v["full"])
            self.bikes_sum += int(v["bikes"])
            self.docks_sum += int(v["docks"])
            self.mechanical_sum += int(v["mechanical"])
            self.electric_sum += int(v["electric"])
            self.lag_sum += int(v["lag"])
            if raw["station_reported_at"] is not None:
                self.reported_stamps.add(iso(as_utc(raw["station_reported_at"])))

    def fields(self):
        def avg(total):
            return round(total / self.usable, 4) if self.usable else None
        return {
            "samples": self.samples, "usable_samples": self.usable,
            "sum_bikes_available": self.bikes_sum,
            "sum_docks_available": self.docks_sum,
            "sum_mechanical_available": self.mechanical_sum,
            "sum_ebikes_available": self.electric_sum,
            "invalid_samples": self.samples-self.usable,
            "empty_samples": self.empty, "full_samples": self.full,
            "avg_bikes_available": avg(self.bikes_sum),
            "avg_docks_available": avg(self.docks_sum),
            "avg_mechanical_available": avg(self.mechanical_sum),
            "avg_ebikes_available": avg(self.electric_sum),
            "avg_station_report_lag_seconds": avg(self.lag_sum),
            "distinct_station_reports": len(self.reported_stamps),
        }


TABLES = {
    "dim_station": ["station_id", "station_code", "station_name", "latitude", "longitude", "capacity", "first_seen_at", "last_seen_at"],
    "dim_date": ["local_date", "year", "month", "month_name", "day_of_week", "is_weekend"],
    "fact_station_hourly": ["station_id", "utc_hour_start", "local_date", "local_hour", "utc_offset_minutes", "samples", "usable_samples", "invalid_samples", "empty_samples", "full_samples", "sum_bikes_available", "sum_docks_available", "sum_mechanical_available", "sum_ebikes_available", "avg_bikes_available", "avg_docks_available", "avg_mechanical_available", "avg_ebikes_available", "avg_station_report_lag_seconds", "distinct_station_reports"],
    "fact_station_daily": ["station_id", "local_date", "samples", "usable_samples", "invalid_samples", "empty_samples", "full_samples", "sum_bikes_available", "sum_docks_available", "sum_mechanical_available", "sum_ebikes_available", "avg_bikes_available", "avg_docks_available", "avg_mechanical_available", "avg_ebikes_available", "avg_station_report_lag_seconds", "distinct_station_reports"],
    "fact_network_hourly": ["utc_hour_start", "local_date", "local_hour", "utc_offset_minutes", "observed_stations", "samples", "usable_samples", "invalid_samples", "empty_samples", "full_samples", "sum_bikes_available", "sum_docks_available", "avg_bikes_available", "avg_docks_available"],
    "fact_station_latest": ["station_id", "collected_at", "feed_updated_at", "station_reported_at", "num_bikes_available", "num_docks_available", "mechanical_bikes", "electric_bikes", "reported_lag_seconds", "is_usable", "is_installed", "is_renting", "is_returning"],
    "fact_issues": ["run_id", "station_id", "issue_code", "severity", "details"],
    "fact_runs": ["run_id", "started_at", "finished_at", "status", "station_information_count", "station_status_count", "inserted_status_count", "issue_count", "error"],
    "fact_capture_intervals": ["run_id", "captured_at", "previous_captured_at", "gap_minutes", "gap_over_10_minutes"],
}


def csv_write(directory: Path, name: str, rows):
    path = directory / f"{name}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        out = csv.DictWriter(fp, fieldnames=TABLES[name], extrasaction="ignore", lineterminator="\n")
        out.writeheader()
        for row in rows:
            out.writerow({k: row.get(k) for k in TABLES[name]})
    return path


def iter_rows(conn, sql: str, params: dict):
    result = conn.execution_options(yield_per=5000).execute(text(sql), params)
    for row in result.mappings():
        yield dict(row)


def build_export(database_url: str, output_dir: Path, *, start: date | None = None,
                 end: date | None = None, include_samples: bool = False) -> dict:
    """Build from an existing P3 DB. Start/end are inclusive UTC collection dates.

    Runtime is bounded by source rows. No network or permanent DB writes occur.
    The sampled view is intentionally not a per-minute continuous time series.
    """
    if start and end and start > end:
        raise ValueError("start date must be <= end date")
    if (start is None) != (end is None):
        raise ValueError("start and end must both be provided, or both omitted")
    output_dir.mkdir(parents=True, exist_ok=True)
    lower = datetime.combine(start, datetime.min.time(), timezone.utc) if start else None
    upper = datetime.combine(end+timedelta(days=1), datetime.min.time(), timezone.utc) if end else None
    low_s, high_s = iso(lower) if lower else None, iso(upper) if upper else None
    filter_sql = (" AND f.collected_at >= :start AND f.collected_at < :end" if start else "")
    run_filter_sql = (" AND r.started_at >= :start AND r.started_at < :end" if start else "")
    params = ({"start": lower, "end": upper} if database_url.startswith("postgresql") else {"start": low_s, "end": high_s}) if start else {}
    # Note: no synthetic output if no successful observations exist.
    engine = make_engine(database_url)
    try:
        hourly: dict[tuple[int, datetime], Bucket] = defaultdict(Bucket)
        daily: dict[tuple[int, date], Bucket] = defaultdict(Bucket)
        latest = {}
        hours_seen: dict[datetime, set[int]] = defaultdict(set)
        stations_seen: set[int] = set()
        run_ids: set[str] = set()
        first_capture = last_capture = None
        optional_samples = None
        with engine.connect() as conn:
            stations = list(iter_rows(conn, "SELECT * FROM dim_stations ORDER BY station_id", {}))
            raw = iter_rows(conn, f"""
                SELECT f.* FROM fact_station_status f JOIN ingestion_runs r ON r.run_id=f.run_id
                WHERE r.status='success' {filter_sql}
                ORDER BY f.collected_at, f.id
            """, params)
            samples_path = output_dir / "fact_observations.csv" if include_samples else None
            if include_samples:
                optional_samples = samples_path.open("w", encoding="utf-8-sig", newline="")
                sample_fields = ["run_id", "station_id", "collected_at", "station_reported_at", "num_bikes_available", "num_docks_available", "is_usable"]
                sample_writer = csv.DictWriter(optional_samples, fieldnames=sample_fields, extrasaction="ignore")
                sample_writer.writeheader()
            try:
                for f in raw:
                    moment = as_utc(f["collected_at"])
                    hour = hour_start(moment)
                    local = moment.astimezone(PARIS)
                    sd = int(f["station_id"])
                    hk = (sd, hour)
                    dk = (sd, local.date())
                    hourly[hk].add(f)
                    daily[dk].add(f)
                    hours_seen[hour].add(sd)
                    stations_seen.add(sd)
                    run_ids.add(f["run_id"])
                    if first_capture is None:
                        first_capture = moment
                    last_capture = moment
                    # Ordered by time, then row ID: last observed capture wins.
                    latest[sd] = f
                    if include_samples:
                        sample_writer.writerow({key: f.get(key) for key in sample_fields})
            finally:
                if optional_samples:
                    optional_samples.close()
            active = sorted(stations_seen)
            csv_write(output_dir, "dim_station", (s for s in stations if int(s["station_id"]) in stations_seen))
            dates = sorted({d for _, d in daily})
            csv_write(output_dir, "dim_date", ({"local_date": str(d), "year": d.year,
                                                  "month": d.month, "month_name": d.strftime("%B"),
                                                  "day_of_week": d.weekday()+1,
                                                  "is_weekend": int(d.weekday()>=5)} for d in dates))

            def time_fields(hour):
                local = hour.astimezone(PARIS)
                return {"utc_hour_start": iso(hour), "local_date": str(local.date()),
                        "local_hour": local.hour, "utc_offset_minutes": int(local.utcoffset().total_seconds()/60)}

            csv_write(output_dir, "fact_station_hourly", (
                {"station_id": sid, **time_fields(hour), **bucket.fields()}
                for (sid, hour), bucket in sorted(hourly.items())
            ))
            csv_write(output_dir, "fact_station_daily", (
                {"station_id": sid, "local_date": str(day), **bucket.fields()}
                for (sid, day), bucket in sorted(daily.items())
            ))
            network = defaultdict(Bucket)
            # Network-wide average is over *qualified observations* (not average
            # of rounded station averages, nor unique stations/duration).
            for (sid, h), bucket in hourly.items():
                net = network[h]
                net.samples += bucket.samples
                net.usable += bucket.usable
                net.empty += bucket.empty
                net.full += bucket.full
                net.bikes_sum += bucket.bikes_sum
                net.docks_sum += bucket.docks_sum
            csv_write(output_dir, "fact_network_hourly", (
                {**time_fields(hour), "observed_stations": len(hours_seen[hour]),
                 **network[hour].fields()}
                for hour in sorted(network)
            ))
            csv_write(output_dir, "fact_station_latest", (latest[sid] for sid in active))

            # Date filtering uses bound values; runs show failures as well as successes.
            runs = list(iter_rows(conn, f"""
                    SELECT r.* FROM ingestion_runs r
                    WHERE 1=1 {run_filter_sql}
                    ORDER BY r.started_at, r.run_id
                """, params))
            csv_write(output_dir, "fact_runs", runs)
            prior = None
            intervals = []
            for run in runs:
                if run["status"] != "success" or run["run_id"] not in run_ids:
                    continue
                current = as_utc(run["started_at"])
                delta = (current-prior).total_seconds()/60 if prior is not None else None
                intervals.append({"run_id": run["run_id"], "captured_at": iso(current),
                                  "previous_captured_at": iso(prior) if prior else None,
                                  "gap_minutes": round(delta, 3) if delta is not None else None,
                                  "gap_over_10_minutes": int(delta > 10) if delta is not None else None})
                prior = current
            csv_write(output_dir, "fact_capture_intervals", intervals)
            # Filters issues to selected captures, avoiding issues from other periods.
            csv_write(output_dir, "fact_issues", (
                row for row in iter_rows(conn, f"""
                    SELECT q.run_id, q.station_id, q.issue_code, q.severity, q.details
                    FROM data_quality_issues q
                    JOIN ingestion_runs r ON r.run_id=q.run_id
                    WHERE r.status='success' {run_filter_sql}
                    ORDER BY r.started_at, q.id
                """, params)
            ))
        file_manifest = {}
        for name in [*TABLES, *( ["fact_observations"] if include_samples else [])]:
            p = output_dir / f"{name}.csv"
            with p.open("rb") as file:
                checksum = hashlib.sha256(file.read()).hexdigest()
            with p.open("r", encoding="utf-8-sig", newline="") as file:
                count = sum(1 for _ in file)-1
            file_manifest[name] = {"rows": count, "sha256": checksum, "file": p.name}
        meta = {
            "project": "Urban Ops Mobility Intelligence",
            "phase": "P4 — Analytics / Power BI",
            "data_origin": "P3 archived Vélib' feeds replayed to SQL; no fabricated observations",
            "time_zone": "Europe/Paris (hourly bucket stored as distinct UTC hour + offset)",
            "from_utc": iso(first_capture) if first_capture else None,
            "through_utc": iso(last_capture) if last_capture else None,
            "query_start_utc": str(start) if start else None,
            "query_end_utc": str(end) if end else None,
            "unique_collections": len(run_ids),
            "unique_stations_observed": len(stations_seen),
            "has_usable_history": bool(run_ids),
            "limitations": [
                "A rate is a proportion of qualifying captured observations, not a time duration.",
                "No journey, trip, demand, rebalancing or service-level savings can be inferred.",
                "GitHub Actions schedule is best-effort; missing intervals are not interpolated.",
                "Metadata station capacity/name is latest known (slowly changing type 1).",
                "Station averages are sample-weighted, not station-weighted.",
                "Latest is as of the exported dataset, not necessarily the present time.",
                "A single date/hour is insufficient for trend or predictive conclusions.",
            ],
            "tables": file_manifest,
        }
        (output_dir / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        return meta
    finally:
        engine.dispose()