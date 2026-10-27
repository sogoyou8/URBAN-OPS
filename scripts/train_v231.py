"""Offline V2.3.1: compare cautious forecast methods on verified Vélib' P3.

Intentionally does not read the old P5 test block. It never saves model weights,
station predictions, or anything that can be published on Vercel. A new future
independent chronological test is required for V2.4.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.p5_exploratory import verified_replay
from urban_ops.p5 import readiness, sql_observations, successful_captures
from urban_ops.v23_candidates import collect_v23_splits
from urban_ops.v231_stability import compare_stability_methods

BANNED = ("model.joblib", "station_forecasts_30m.csv", "v2_model.joblib",
          "v2_station_forecasts.csv", "trained_model.pkl")


def run(db_url: str, replay_evidence: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if any((out / filename).exists() for filename in BANNED):
        raise ValueError("Research output may not contain deployable models or forecasts")
    verified = verified_replay(replay_evidence)
    captures = successful_captures(db_url)
    readiness_gate = readiness(captures)
    result = {
        "phase": "Urban Ops V2.3.1 — stability-aware research candidates only",
        "status": "not_ready",
        "source": "P3 real history restored with SHA-256 checked releases",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified_archives": verified,
        "history_gate": readiness_gate,
        "models_compared": [
            "persistence",
            "residual_ml",
            "v23_conservative",
            "simple_bounded_trend",
            "classified_stability_gate",
        ],
        "old_test_block_not_read": True,
        "new_independent_future_test_required": True,
        "data_not_realtime": True,
        "public_v1_changed": False,
        "model_exported": False,
        "forecast_exported": False,
        "safe_to_publish_forecasts": False,
    }
    if not readiness_gate["ready"] or verified < 900:
        result["reason"] = "Insufficient verified real-history evidence"
    else:
        samples, (validation_start, old_test_start) = collect_v23_splits(
            sql_observations(db_url), captures,
            max_train=90_000, max_validation=20_000,
        )
        result["split_boundaries_utc"] = {
            "historical_validation_start": validation_start.isoformat(),
            "old_test_start_EXCLUDED": old_test_start.isoformat(),
        }
        result["samples"] = {
            k: {"eligible": v.seen, "sampled": len(v.items)}
            for k, v in samples.items()
        }
        result["comparison"] = compare_stability_methods(
            samples["train"].items, samples["validation"].items, captures
        )
        result["status"] = result["comparison"]["status"]
    target = out / "V2_3_1_STABILITY_COMPARISON.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="V2.3.1 no-deployment offline stability research")
    parser.add_argument("--db-url", default="sqlite:///./data/v231-history.sqlite")
    parser.add_argument("--replay-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/v231-research"))
    args = parser.parse_args()
    result = run(args.db_url, args.replay_evidence, args.output)
    print(json.dumps({
        "status": result["status"],
        "verified_archives": result["verified_archives"],
        "safe_to_publish_forecasts": result["safe_to_publish_forecasts"],
        "comparison": result.get("comparison", {}).get("historical_validation"),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
