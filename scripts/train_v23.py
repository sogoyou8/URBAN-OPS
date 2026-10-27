"""Execute V2.3 candidate comparison from SHA-checked real P3 replays.

Separate research branch only. Evaluates the existing validation block, never
the previously inspected test block, and exports JSON metrics only.
No model, station-level predictions or public UI changes are created.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.p5_exploratory import verified_replay
from urban_ops.p5 import readiness, sql_observations, successful_captures
from urban_ops.v23_candidates import collect_v23_splits, compare_candidates

BANNED_FILES = ("model.joblib", "station_forecasts_30m.csv",
                "v2_model.joblib", "v2_station_forecasts.csv")


def run(database_url: str, replay_evidence: Path, out: Path) -> dict:
    # Refuse even accidental reuse of a publishable model output directory.
    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).exists() for name in BANNED_FILES):
        raise ValueError("V2.3 output cannot contain models or station forecasts")

    verified_count = verified_replay(replay_evidence)
    captures = successful_captures(database_url)
    gate = readiness(captures)
    report = {
        "phase": "Urban Ops V2.3 — research comparison only",
        "status": "not_ready",
        "source": "P3 real captures restored from checksum-verified GitHub Releases",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verified_archive_replays": verified_count,
        "history_gate": gate,
        "candidate_methods": [
            "persistence_tplus30_equals_now",
            "hist_gradient_boosting_absolute_error_regression_of_delta",
            "calibration_selected_shrinkage_and_minimum_predicted_correction",
        ],
        "research_isolated_from_public_v1": True,
        "no_old_p5_test_used_for_tuning_or_reporting": True,
        "future_independent_holdout_required": True,
        "no_deployment": True,
        "model_exported": False,
        "station_forecasts_exported": False,
        "safe_to_publish_forecasts": False,
    }
    if not gate["ready"] or verified_count < 900:
        report["reason"] = "insufficient_sha_verified_real_archive_history"
    else:
        splits, (validation_start, test_start) = collect_v23_splits(
            sql_observations(database_url), captures,
            max_train=90_000, max_validation=20_000
        )
        report["split_boundaries_utc"] = {
            "validation_start": validation_start.isoformat(),
            "old_test_start_not_evaluated": test_start.isoformat(),
        }
        report["paired_examples"] = {
            name: {"eligible": series.seen, "sampled": len(series.items)}
            for name, series in splits.items()
        }
        report["comparison"] = compare_candidates(
            splits["train"].items, splits["validation"].items, captures
        )
        report["status"] = report["comparison"]["status"]
    (out / "V2_3_RESEARCH_COMPARISON.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="V2.3 no-deploy candidate comparison")
    parser.add_argument("--db-url", default="sqlite:///./data/v23-history.sqlite")
    parser.add_argument("--replay-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/v23-research"))
    args = parser.parse_args()
    result = run(args.db_url, args.replay_evidence, args.output)
    print(json.dumps({
        "status": result["status"],
        "verified_real_captures": result["verified_archive_replays"],
        "safe_to_publish_forecasts": result["safe_to_publish_forecasts"],
        "output": str(args.output),
        "validation": result.get("comparison", {}).get("outer_validation"),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
