"""V2.1 real-history diagnostic, V2.2 feature-availability audit.

Investigates why the original P5 model loses to persistence, then measures the
availability of experimental PAST-ONLY features. No model or forecasts saved.
Run only from SHA-verified P3 replays and preserve the untouched public V1.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.p5_exploratory import verified_replay
from urban_ops.p5 import (
    FEATURE_NAMES, collect_splits, evaluate, readiness, sql_observations,
    successful_captures, bounded,
)
from urban_ops.v2_research import FEATURE_NAMES_V2, collect_v2_splits

PARIS = ZoneInfo("Europe/Paris")
MIN_GROUP = 50


def group_summary(rows: list[tuple], *, minimum: int = MIN_GROUP) -> dict:
    if len(rows) < minimum:
        return {"samples": len(rows), "suppressed": True}
    baseline_abs = [abs(y - b) for y, b, _ in rows]
    ml_abs = [abs(y - m) for y, _, m in rows]
    maeb = sum(baseline_abs) / len(rows)
    maem = sum(ml_abs) / len(rows)
    return {
        "samples": len(rows),
        "baseline_mae": round(maeb, 4),
        "incumbent_mae": round(maem, 4),
        "incumbent_minus_baseline_mae": round(maem - maeb, 4),
        "baseline_wins": maeb <= maem,
    }


def validation_segments(examples, predictions) -> dict:
    """Descriptive V2.1 grouping on validation only, never for model selection."""
    sections = defaultdict(list)
    by_station = defaultdict(list)
    for ex, pred in zip(examples, predictions):
        now = ex.values[0]
        actual = ex.target_bikes
        local = ex.feature_at.astimezone(PARIS)
        change = abs(actual - now)
        target = (actual, now, pred)
        segments = (
            ("change_size", "unchanged" if change == 0 else ("1-2" if change <= 2 else "3+")),
            ("time_of_day", "night_0_5" if local.hour < 6 else
             ("morning_6_11" if local.hour < 12 else
              ("afternoon_12_17" if local.hour < 18 else "evening_18_23"))),
            ("day_type", "weekend" if local.weekday() >= 5 else "weekday"),
            ("level_now", "zero" if now == 0 else ("1-5" if now <= 5 else "6+")),
            ("history_5m", "missing" if math.isnan(ex.values[6]) else "present"),
            ("history_15m", "missing" if math.isnan(ex.values[7]) else "present"),
        )
        for category, value in segments:
            sections[(category, value)].append(target)
        by_station[ex.station_id].append(target)
    result = {}
    for (cat, name), rows in sorted(sections.items()):
        result.setdefault(cat, {})[name] = group_summary(rows)
    # Ranking is an error-diagnosis aide only. This is NOT held-out skill.
    qualifying = [(sid, values) for sid, values in by_station.items() if len(values) >= 25]
    qualifying.sort(key=lambda z: (
        group_summary(z[1], minimum=0)["incumbent_minus_baseline_mae"]
    ), reverse=True)
    result["station_cases_validation_only"] = [
        {"station_id": sid, **group_summary(values, minimum=0)}
        for sid, values in qualifying[:12]
    ]
    result["validation_samples_examined"] = len(examples)
    return result


def feature_coverage(sets) -> dict:
    covered = {}
    for name, values in sets.items():
        rows = values.items
        if not rows:
            covered[name] = {"eligible": values.seen, "sampled": 0}
            continue
        missing = {}
        for index, feature in enumerate(FEATURE_NAMES_V2):
            count = sum(not math.isfinite(row.values[index]) for row in rows)
            missing[feature] = round(count / len(rows), 4)
        covered[name] = {
            "eligible": values.seen,
            "sampled": len(rows),
            "missing_fraction": missing,
            "eligible_pair_ratio_is_not_data_completeness": True,
        }
    return covered


def run(db_url: str, replay_evidence: Path, out: Path) -> dict:
    verified = verified_replay(replay_evidence)
    captures = successful_captures(db_url)
    gate = readiness(captures)
    report = {
        "phase": "Urban Ops V2.1 + V2.2 — research diagnostics only",
        "status": "not_ready",
        "source": "P3 SQL rebuilt from SHA-256 checked GitHub Release archives",
        "verified_archive_replays": verified,
        "history_gate": gate,
        "v1_public_deployment_unchanged": True,
        "model_exported": False,
        "forecast_exported": False,
        "safe_to_publish_forecasts": False,
        "validation_policy": (
            "V2.1 diagnostic groups use incumbent's validation period only. "
            "Test period is reported only as aggregate, never used to tune features; "
            "V2.4 must reserve a NEW future period for any promoted V2 candidate."
        ),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not gate["ready"] or verified < 900:
        report["reason"] = "not_enough_verified_real_history"
    else:
        original, _, bounds = collect_splits(sql_observations(db_url), captures)
        report["split_boundaries_utc"] = {
            "validation_start": bounds[0].isoformat(),
            "test_start": bounds[1].isoformat(),
        }
        report["incumbent_feature_names"] = list(FEATURE_NAMES)
        report["split_counts"] = {
            key: {"eligible": value.seen, "sampled": len(value.items)}
            for key, value in original.items()
        }
        if len(original["train"].items) < 5000 or any(
            len(original[key].items) < 1000 for key in ("validation", "test")
        ):
            report["status"] = "insufficient_labeled_pairs"
        else:
            # Diagnostic replication of the ORIGINAL P5 candidate, NOT a V2 fit.
            from sklearn.ensemble import HistGradientBoostingRegressor

            incumbent = HistGradientBoostingRegressor(
                max_iter=120, max_leaf_nodes=24, max_depth=5,
                min_samples_leaf=40, learning_rate=0.08,
                l2_regularization=5.0, random_state=42,
            )
            train = original["train"].items
            incumbent.fit([x.values for x in train], [x.target_bikes for x in train])
            validation = original["validation"].items
            test = original["test"].items
            predicted = bounded(incumbent.predict([x.values for x in validation]), validation)
            report["incumbent_original_algorithm"] = "HistGradientBoostingRegressor"
            report["incumbent_validation"] = evaluate(incumbent, validation)
            report["incumbent_test_aggregate_only"] = evaluate(incumbent, test)
            report["validation_error_segments"] = validation_segments(validation, predicted)

            # Experiment only: recompute past-only V2 *features* on actual
            # chronological observations, no V2 candidate fitted or scored.
            extended, extended_bounds = collect_v2_splits(
                sql_observations(db_url), captures, max_train=10_000, max_eval=5_000
            )
            if extended_bounds != bounds:
                raise ValueError("V2 features have inconsistent temporal boundaries")
            report["v2_added_feature_names"] = list(FEATURE_NAMES_V2[len(FEATURE_NAMES):])
            report["v2_feature_availability"] = feature_coverage(extended)
            report["status"] = "diagnostics_complete_no_v2_training"
            del incumbent  # never serialized or attached to public V1

    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).exists() for name in ("model.joblib", "station_forecasts_30m.csv")):
        raise ValueError("V2 diagnosis refuses output directory containing deployable model/forecasts")
    (out / "V2_1_V2_2_DIAGNOSTICS.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="Urban Ops V2 analysis; never publishes a forecast")
    parser.add_argument("--db-url", default="sqlite:///./data/v2-history.sqlite")
    parser.add_argument("--replay-evidence", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/v2-diagnostics"))
    args = parser.parse_args()
    report = run(args.db_url, args.replay_evidence, args.output)
    print(json.dumps({
        "status": report["status"],
        "verified_archive_replays": report["verified_archive_replays"],
        "history_gate": report["history_gate"]["reason"],
        "public_v1_unchanged": report["v1_public_deployment_unchanged"],
        "safe_to_publish_forecasts": report["safe_to_publish_forecasts"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
