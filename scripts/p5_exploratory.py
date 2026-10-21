"""Exploratory P5 backtest on verified P3 replays, BEFORE seven full days.

Never exports a model, station forecasts, final scores, or promotion decisions.
The seven-day / 900-archive / coverage gates in train_p5 remain unchanged.
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from urban_ops.p5 import (collect_splits, fit_and_score, mae, readiness, rmse,
                          sql_observations, successful_captures)


def verified_replay(path: Path) -> int:
    """Only accept the successful, SHA-checked P3 replay evidence from the CI job."""
    records = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(records, list) or not records
            or any(not isinstance(r, dict) or r.get("status") != "success"
                   or not r.get("run_id") or not r.get("asset") for r in records)):
        raise ValueError("Expected successful checksum-verified P3 replay records")
    ids = [r["run_id"] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate runs in P3 replay evidence")
    return len(records)


def baseline_on(samples) -> dict:
    rows = samples.items
    if not rows:
        return {"pairs": 0, "persistence_mae": None, "persistence_rmse": None}
    real = [x.target_bikes for x in rows]
    simple = [x.values[0] for x in rows]
    return {"pairs": len(rows), "persistence_mae": round(mae(real, simple), 4),
            "persistence_rmse": round(rmse(real, simple), 4)}


def run(database_url: str, out: Path, evidence: Path, *,
        max_train: int = 30_000, max_eval: int = 7_000) -> dict:
    replayed = verified_replay(evidence)
    captures = successful_captures(database_url)
    gate = readiness(captures)
    report = {
        "phase": "P5 +30min — early real-data diagnostic",
        "status": "insufficient_preview_history",
        "production_status": "NOT_VALIDATED",
        "source": "SHA-256 verified P3 replay; station records qualified by P3 is_usable",
        "replay_archives_verified": replayed,
        "release_readiness": gate,
        "forecast_horizon_minutes": 30,
        "prediction_rows": 0,
        "model_exported": False,
        "forecast_exported": False,
        "safe_to_publish_forecasts": False,
        "warning": ("Exploratory result on an incomplete time period. "
                    "Not an estimate of seven-day performance, not a published model."),
        "final_gate": ("Original 7-day, 900 captures, 40% distinct-slot coverage, "
                       "and independent held-out evaluation all remain mandatory."),
    }
    if len(captures) >= 3:
        splits, _, boundaries = collect_splits(sql_observations(database_url),
                                                captures, max_train=max_train,
                                                max_eval=max_eval)
        report["split_boundaries_utc"] = {
            "validation_start": boundaries[0].isoformat(),
            "test_start": boundaries[1].isoformat(),
        }
        report["real_label_pairs"] = {
            k: {"eligible": v.seen, "sampled": len(v.items)} for k, v in splits.items()
        }
        report["baseline_only"] = {
            k: baseline_on(v) for k, v in splits.items() if k in ("validation", "test")
        }
        # A provisional model is informative only with real separated label pairs.
        # Never call the candidate a validated model and never save the fitted object.
        if not gate["ready"]:
            result_model, result = fit_and_score(splits, min_train=1500, min_eval=250)
            del result_model
            if "validation" in result and "holdout" in result:
                report["status"] = "exploratory_only"
                report["provisional_candidate"] = {
                    "algorithm": result.get("candidate"),
                    "validation": result["validation"],
                    "test": result["holdout"],
                    "caveat": "Short-period trial only; numeric advantage is NOT production validation.",
                }
            else:
                report["status"] = "insufficient_preview_pairs"
        else:
            report["status"] = "final_workflow_required"
    out.mkdir(parents=True, exist_ok=True)
    # Guaranteed absence of production-like artifacts, even for a previous run.
    for filename in ("model.joblib", "station_forecasts_30m.csv"):
        existing = out / filename
        if existing.exists():
            raise ValueError(f"Refusing exploratory directory containing {filename}")
    (out / "P5_EXPLORATORY_ONLY.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)+"\n",
        encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Exploratory P5 from verified P3 only; no model exports")
    parser.add_argument("--db-url", default="sqlite:///./data/p6-real.sqlite")
    parser.add_argument("--replay-evidence", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/p5-exploratory"))
    a = parser.parse_args()
    report = run(a.db_url, a.output, a.replay_evidence)
    print(json.dumps({
        "status": report["status"],
        "real_archives": report["replay_archives_verified"],
        "pairs": report.get("real_label_pairs"),
        "production_status": report["production_status"],
        "safe_to_publish_forecasts": report["safe_to_publish_forecasts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
