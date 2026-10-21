"""Forensic summary of P3 runs with no usable stations, from verified replayed SQL.

No API calls and no reinterpretation of source measurements. Issue counts may
overlap; diagnostic flags are potential exclusions, never asserted root causes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from sqlalchemy import text
from urban_ops.storage import make_engine

DEFAULT_MAX_LAG_SECONDS = 3600


def diagnose(database_url: str, max_lag_seconds: int = DEFAULT_MAX_LAG_SECONDS) -> dict:
    if max_lag_seconds <= 0:
        raise ValueError("max_lag_seconds must be positive")
    engine = make_engine(database_url)
    try:
        with engine.connect() as conn:
            runs = [dict(r) for r in conn.execute(text("""
                SELECT r.run_id, r.started_at, r.station_information_count,
                       r.station_status_count, r.inserted_status_count,
                       COUNT(f.station_id) AS observed,
                       SUM(CASE WHEN f.is_usable=1 THEN 1 ELSE 0 END) AS usable
                FROM ingestion_runs r
                LEFT JOIN fact_station_status f ON f.run_id=r.run_id
                WHERE r.status='success'
                GROUP BY r.run_id
                ORDER BY r.started_at
            """)).mappings()]
            anomalies = []
            for i, run in enumerate(runs):
                if int(run["observed"] or 0) == 0 or int(run["usable"] or 0) != 0:
                    continue
                rid = run["run_id"]
                detail = conn.execute(text("""
                    SELECT COUNT(*) AS recorded,
                      SUM(CASE WHEN is_installed!=1 OR is_installed IS NULL THEN 1 ELSE 0 END) AS not_installed,
                      SUM(CASE WHEN is_renting!=1 OR is_renting IS NULL THEN 1 ELSE 0 END) AS not_renting,
                      SUM(CASE WHEN is_returning!=1 OR is_returning IS NULL THEN 1 ELSE 0 END) AS not_returning,
                      SUM(CASE WHEN reported_lag_seconds IS NULL THEN 1 ELSE 0 END) AS missing_lag,
                      SUM(CASE WHEN reported_lag_seconds < 0 THEN 1 ELSE 0 END) AS future_report,
                      SUM(CASE WHEN reported_lag_seconds > :max_lag THEN 1 ELSE 0 END) AS stale_report,
                      SUM(CASE WHEN num_bikes_available IS NULL OR num_docks_available IS NULL
                            OR mechanical_bikes IS NULL OR electric_bikes IS NULL THEN 1 ELSE 0 END) AS missing_counts,
                      SUM(CASE WHEN num_bikes_available IS NULL THEN 1 ELSE 0 END) AS missing_total_bikes,
                      SUM(CASE WHEN num_docks_available IS NULL THEN 1 ELSE 0 END) AS missing_total_docks,
                      SUM(CASE WHEN mechanical_bikes IS NULL THEN 1 ELSE 0 END) AS missing_mechanical_bikes,
                      SUM(CASE WHEN electric_bikes IS NULL THEN 1 ELSE 0 END) AS missing_electric_bikes,
                      SUM(CASE WHEN num_bikes_available IS NOT NULL
                            AND mechanical_bikes IS NOT NULL AND electric_bikes IS NOT NULL
                            AND num_bikes_available!=mechanical_bikes+electric_bikes THEN 1 ELSE 0 END) AS bike_type_mismatch,
                      MIN(reported_lag_seconds) AS min_report_lag_seconds,
                      MAX(reported_lag_seconds) AS max_report_lag_seconds,
                      MIN(feed_updated_at) AS feed_updated_min,
                      MAX(feed_updated_at) AS feed_updated_max
                    FROM fact_station_status WHERE run_id=:rid
                """), {"rid":rid,"max_lag":max_lag_seconds}).mappings().one()
                counts = [dict(r) for r in conn.execute(text("""
                    SELECT issue_code, COUNT(*) AS count
                    FROM data_quality_issues WHERE run_id=:rid
                    GROUP BY issue_code ORDER BY count DESC, issue_code
                """), {"rid":rid}).mappings()]
                def neighbor(index: int):
                    if not 0 <= index < len(runs):
                        return None
                    x = runs[index]
                    return {"at":str(x["started_at"]),"observed":int(x["observed"] or 0),
                            "usable":int(x["usable"] or 0)}
                anomalies.append({
                    "at": str(run["started_at"]),
                    "observed":int(run["observed"] or 0),"usable":0,
                    "source_status_count": run["station_status_count"],
                    "source_information_count":run["station_information_count"],
                    "normalized_status_count":run["inserted_status_count"],
                    "previous_run":neighbor(i-1),"following_run":neighbor(i+1),
                    "diagnostic_factors_not_mutually_exclusive":
                        {key:(int(value or 0) if key not in ("min_report_lag_seconds",
                          "max_report_lag_seconds","feed_updated_min","feed_updated_max") else value)
                         for key,value in dict(detail).items()},
                    "issue_counts_not_distinct_station_counts":
                        [{"code":x["issue_code"],"events":int(x["count"])} for x in counts],
                })
            return {"status":"anomalies_detected" if anomalies else "no_zero_usable_runs_in_replay",
                    "runs_examined":len(runs),"max_lag_seconds":max_lag_seconds,
                    "anomalies":anomalies,
                    "note":"Diagnose only: counts can overlap and do not establish a single root cause. "
                           "Raw Bronze payloads and timestamps are preserved in the P3 archives."}
    finally:
        engine.dispose()


def main(argv=None):
    parser=argparse.ArgumentParser(description="Inspect zero-usable-station P3 collections in replayed SQL")
    parser.add_argument("--db-url",default="sqlite:///./data/p6-real.sqlite")
    parser.add_argument("--max-lag-seconds",type=int,default=DEFAULT_MAX_LAG_SECONDS)
    parser.add_argument("--output",type=Path,default=Path("data/p6-quality-diagnostic.json"))
    args=parser.parse_args(argv)
    result=diagnose(args.db_url,args.max_lag_seconds)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,default=str))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
