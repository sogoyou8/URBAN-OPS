"""Run honest P5 forecasting from P3 SQLite/PostgreSQL observations.

Exit 0 with a transparent NOT_READY status when historical evidence is thin.
No model or forecast is written in that case.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import timedelta
from pathlib import Path

from urban_ops.p5 import (FEATURE_NAMES, HORIZON, TOLERANCE, collect_splits,
                          fit_and_score, readiness, sql_observations,
                          successful_captures)


def run(database_url: str, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    captures = successful_captures(database_url)
    gate = readiness(captures)
    result = {
        "phase": "P5 — 30-minute station bike availability forecasting",
        "source": "P3 qualified observations from a provided SQL database",
        "origin_verified_by_p5": False,
        "actual_forecast_horizon_minutes": int(HORIZON.total_seconds() / 60),
        "allowed_target_timing_deviation_minutes": int(TOLERANCE.total_seconds() / 60),
        "target": "observed_num_bikes_available_t_plus_30m_not_demand_or_trips",
        "leakage_controls": [
            "Only P3 is_usable observations yield model inputs and future target labels",
            "No missing snapshots or target values interpolated",
            "Chronological 60/20/20 split by capture UTC with 30-minute target-time purge",
            "No feature may use data observed later than its feature_at timestamp",
            "Holdout period never used to fit or tune model hyperparameters",
        ],
        "data_readiness": gate,
        "feature_names": list(FEATURE_NAMES),
    }
    if not gate["ready"]:
        result["status"] = "not_ready"
        result["reason"] = gate["reason"]
    else:
        sets, latest, bounds = collect_splits(sql_observations(database_url), captures)
        model, report = fit_and_score(sets)
        result.update(report)
        result["chronological_boundaries_utc"] = {
            "validation_start": bounds[0].isoformat(),
            "test_start": bounds[1].isoformat(),
        }
        if model is not None:
            from joblib import dump
            dump({"model": model, "feature_names": FEATURE_NAMES,
                  "horizon_minutes": 30}, out / "model.joblib")
            # This dataset's *latest* station snapshot can be historical when
            # opening the report. These are forecasts as-of, NOT live guarantees.
            predictions = []
            for current in latest.values():
                value = float(model.predict([current.values])[0])
                predictions.append({
                    "station_id": current.station_id,
                    "as_of_utc": current.feature_at.isoformat(),
                    "target_utc": (current.feature_at + timedelta(minutes=30)).isoformat(),
                    "bikes_at_capture": int(current.values[0]),
                    "predicted_bikes_tplus30": round(max(0.0, min(float(current.capacity), value)), 2),
                    "model_type": "hist_gradient_boosting",
                    "not_a_probability_or_demand_measure": 1,
                })
            with (out / "station_forecasts_30m.csv").open("w", encoding="utf-8-sig", newline="") as fp:
                writer = csv.DictWriter(fp, fieldnames=[
                    "station_id", "as_of_utc", "target_utc", "bikes_at_capture",
                    "predicted_bikes_tplus30", "model_type", "not_a_probability_or_demand_measure",
                ])
                writer.writeheader()
                writer.writerows(sorted(predictions, key=lambda x: x["station_id"]))
            result["forecast_rows"] = len(predictions)
            result["forecast_is_live"] = False
        else:
            result["model_written"] = False
            result["forecast_rows"] = 0
    (out / "P5_STATUS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", default="sqlite:///./data/p5-history.sqlite")
    parser.add_argument("--output", type=Path, default=Path("data/p5-output"))
    args = parser.parse_args()
    d = run(args.db_url, args.output)
    print(json.dumps({"status": d["status"], "reason": d.get("reason"),
                      "captures": d["data_readiness"]["captures"],
                      "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()