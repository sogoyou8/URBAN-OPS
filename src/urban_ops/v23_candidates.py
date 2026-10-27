"""Urban Ops V2.3 — non-deployable, chronological candidate comparison.

Candidates: persistence, regression of the future-minus-current bicycle count,
and an explicitly conservative (shrunken/gated) residual correction.

Only past/training observations set coefficients and correction thresholds.
The prior P5 test set is NEVER loaded or evaluated by this module. V2.4
requires a fresh, future, truly untouched test period before any promotion.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Iterable

from .p5 import Example, HORIZON, Reservoir, Observation, readiness, split_limits, utc
from .v2_research import FEATURE_NAMES_V2, stream_v2_examples

MODEL_PARAMETERS = {
    "loss": "absolute_error",
    "max_iter": 100,
    "max_leaf_nodes": 20,
    "max_depth": 4,
    "min_samples_leaf": 50,
    "learning_rate": 0.06,
    "l2_regularization": 8.0,
    "early_stopping": False,  # sklearn random holdout would ignore chronology
    "random_state": 42,
}
SHRINKAGES = (0.25, 0.5, 0.75, 1.0)
MINIMUM_ABSOLUTE_CORRECTION = (0.0, 0.5, 1.0, 1.5, 2.0)


def collect_v23_splits(observations: Iterable[Observation], captures: Iterable,
                       *, max_train: int = 90000, max_validation: int = 20000):
    """No reservoir for the existing test block; never even inspect its labels.

    The train/validation bounds reproduce the P5 chronological 60/20/20 and
    purge labels whose target crosses either boundary.
    """
    validation_start, test_start = split_limits(captures)
    buckets = {
        "train": Reservoir(max_train, 301),
        "validation": Reservoir(max_validation, 302),
    }
    for _features, ex in stream_v2_examples(observations):
        if ex is None:
            continue
        if ex.feature_at < validation_start and ex.target_at < validation_start:
            buckets["train"].add(ex)
        elif validation_start <= ex.feature_at < test_start and ex.target_at < test_start:
            buckets["validation"].add(ex)
        # Existing test records are intentionally not retained or inspected.
    return buckets, (validation_start, test_start)


def inner_cutoff(captures: Iterable, validation_start):
    """Chronological core fit / calibration boundary wholly inside train."""
    times = sorted({utc(t) for t in captures})
    cutoff = times[0] + (validation_start - times[0]) * 0.80
    if not times[0] < cutoff < validation_start - HORIZON:
        raise ValueError("Training period too short for purged inner calibration")
    return cutoff


def partition_training(train: list[Example], cutoff):
    core = [x for x in train if x.feature_at < cutoff and x.target_at < cutoff]
    calibration = [x for x in train if x.feature_at >= cutoff]
    if any(x.target_at >= cutoff for x in core):
        raise ValueError("Training label crosses internal cutoff")
    if any(x.feature_at < cutoff for x in calibration):
        raise ValueError("Calibration starts before internal cutoff")
    return core, calibration


def clamp(ex: Example, proposed: float) -> float:
    """Bike counts are physically bounded by known capacity."""
    capacity = ex.values[2]
    if not math.isfinite(capacity) or capacity <= 0:
        raise ValueError("Unusable station capacity in research example")
    return max(0.0, min(float(capacity), float(proposed)))


def corrected(ex: Example, predicted_delta: float, *, alpha=1.0, threshold=0.0) -> float:
    """Threshold tests predicted change ONLY, not unknowable future truth."""
    if alpha == 0 or abs(predicted_delta) <= threshold:
        return float(ex.values[0])
    return clamp(ex, float(ex.values[0]) + alpha * predicted_delta)


def predictions_for(examples: list[Example], deltas: Iterable[float], *,
                    alpha: float, threshold: float) -> list[float]:
    deltas = list(deltas)
    if len(deltas) != len(examples):
        raise ValueError("Misaligned predictions and true pairs")
    return [
        corrected(ex, float(delta), alpha=alpha, threshold=threshold)
        for ex, delta in zip(examples, deltas)
    ]


def score(examples: list[Example], predicted: list[float]) -> dict:
    if not examples or len(examples) != len(predicted):
        raise ValueError("Metrics require aligned, non-empty measured targets")
    errors = [float(ex.target_bikes) - float(pred) for ex, pred in zip(examples, predicted)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    changed = sum(abs(float(ex.values[0]) - pred) > 1e-9
                  for ex, pred in zip(examples, predicted))
    return {
        "pairs": len(examples),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "prediction_changes_share": round(changed / len(examples), 4),
    }


def choose_conservative_rule(calibration: list[Example], predicted_delta: Iterable[float]):
    """One fixed grid, selected ONLY on internal train-time calibration.

    Includes zero correction as a valid outcome: if the baseline is best,
    we transparently retain persistence rather than invent an improvement.
    """
    predicted_delta = list(predicted_delta)
    baseline = score(calibration, [float(x.values[0]) for x in calibration])
    possibilities = [(0.0, 0.0)] + [
        (alpha, threshold)
        for alpha in SHRINKAGES for threshold in MINIMUM_ABSOLUTE_CORRECTION
    ]
    candidates = []
    for alpha, threshold in possibilities:
        pred = predictions_for(calibration, predicted_delta,
                               alpha=alpha, threshold=threshold)
        result = score(calibration, pred)
        candidates.append((result["mae"], result["prediction_changes_share"],
                           alpha, threshold))
    # If rounded MAE ties, favor fewer unnecessary corrections.
    best = min(candidates, key=lambda v: (v[0], v[1], v[2], -v[3]))
    return {
        "alpha": best[2],
        "minimum_absolute_correction_bikes": best[3],
        "baseline_calibration": baseline,
        "chosen_calibration": score(
            calibration,
            predictions_for(calibration, predicted_delta,
                            alpha=best[2], threshold=best[3]),
        ),
        "grid_size": len(possibilities),
        "selection_only_used_internal_training_calibration": True,
    }


def day_coverage(examples: list[Example]) -> dict:
    from zoneinfo import ZoneInfo
    paris = ZoneInfo("Europe/Paris")
    dates = sorted({x.feature_at.astimezone(paris).date().isoformat()
                    for x in examples})
    weekdays = sum(x.feature_at.astimezone(paris).weekday() < 5 for x in examples)
    return {
        "calendar_dates_paris": dates,
        "weekday_examples": weekdays,
        "weekend_examples": len(examples) - weekdays,
        "caution": "Validation composition alone cannot establish future-week generalization.",
    }


def validation_segments(examples: list[Example], predictions: dict) -> dict:
    """POST-OUTCOME descriptive reporting; never used for candidate tuning."""
    output = {}
    for label, test in (
        ("truly_unchanged", lambda x: x.target_bikes == x.values[0]),
        ("truly_changed", lambda x: x.target_bikes != x.values[0]),
    ):
        indices = [i for i, x in enumerate(examples) if test(x)]
        if len(indices) < 50:
            output[label] = {"pairs": len(indices), "suppressed": True}
            continue
        subset = [examples[i] for i in indices]
        output[label] = {
            name: score(subset, [values[i] for i in indices])
            for name, values in predictions.items()
        }
    return output


def compare_candidates(train: list[Example], validation: list[Example],
                       captures: Iterable, *, min_core: int = 5000,
                       min_calibration: int = 1000,
                       min_validation: int = 1000) -> dict:
    """Fit on chronological train-core, choose filter on train-calibration.

    The outer VALIDATION is touched only once for final V2.3 comparison.
    No old P5 holdout is read and no trained object is returned or serialized.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    capture_times = list(captures)
    boundary, _test = split_limits(capture_times)
    if any(x.feature_at >= boundary or x.target_at >= boundary for x in train):
        raise ValueError("Training contains observations across outer validation")
    if any(x.feature_at < boundary for x in validation):
        raise ValueError("Validation leaked into training block")
    core, calibration = partition_training(train, inner_cutoff(capture_times, boundary))
    if len(core) < min_core or len(calibration) < min_calibration or len(validation) < min_validation:
        return {
            "status": "insufficient_labeled_pairs",
            "core": len(core), "calibration": len(calibration),
            "validation": len(validation),
        }
    if any(len(x.values) != len(FEATURE_NAMES_V2)
           for x in core + calibration + validation):
        raise ValueError("Feature schema drift in V2.3 samples")
    for label, examples in (("core", core), ("calibration", calibration),
                            ("validation", validation)):
        if not all(math.isfinite(ex.values[0])
                   and math.isfinite(ex.values[2])
                   and math.isfinite(ex.target_bikes) for ex in examples):
            raise ValueError("Invalid actual qualified bike counts in " + label)

    estimator = HistGradientBoostingRegressor(**MODEL_PARAMETERS)
    estimator.fit(
        [ex.values for ex in core],
        [float(ex.target_bikes) - float(ex.values[0]) for ex in core],
    )
    deltas_calibration = estimator.predict([ex.values for ex in calibration])
    deltas_validation = estimator.predict([ex.values for ex in validation])
    rule = choose_conservative_rule(calibration, deltas_calibration)

    baseline_predictions = [float(ex.values[0]) for ex in validation]
    raw_predictions = predictions_for(validation, deltas_validation,
                                      alpha=1.0, threshold=0.0)
    cautious_predictions = predictions_for(
        validation, deltas_validation,
        alpha=rule["alpha"],
        threshold=rule["minimum_absolute_correction_bikes"],
    )
    predictions = {
        "persistence": baseline_predictions,
        "residual_ml": raw_predictions,
        "conservative_residual": cautious_predictions,
    }
    comparisons = {key: score(validation, values)
                   for key, values in predictions.items()}
    baseline_mae = comparisons["persistence"]["mae"]
    for key in ("residual_ml", "conservative_residual"):
        comparisons[key]["mae_gain_vs_persistence"] = (
            round(1 - comparisons[key]["mae"] / baseline_mae, 4)
            if baseline_mae else None
        )
    report = {
        "status": "compared_on_existing_validation_only",
        "algorithm": "HistGradientBoostingRegressor of delta_bikes_tplus30",
        "algorithm_configuration": MODEL_PARAMETERS,
        "features": list(FEATURE_NAMES_V2),
        "core_train_rows": len(core),
        "internal_calibration_rows": len(calibration),
        "outer_validation_rows": len(validation),
        "internal_calibration_rule": rule,
        "outer_validation": comparisons,
        "outer_validation_day_coverage": day_coverage(validation),
        "outer_validation_post_outcome_segments": validation_segments(
            validation, predictions
        ),
        "no_old_test_evaluated": True,
        "new_unseen_future_test_required_before_promotion": True,
        "model_saved": False,
        "forecast_saved": False,
        "safe_to_publish_forecasts": False,
    }
    return report
