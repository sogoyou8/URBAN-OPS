"""V2.3.1: offline stability-aware +30 minute candidate comparison.

No publication, no model serialization, no previously inspected P5 test set.
Only earlier TRAIN-core fits models. Train-calibration chooses all candidate
thresholds; historical outer validation is read for one descriptive scorecard.
A genuinely later, unseen V2.4 test is mandatory for promotion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from .p5 import Example, split_limits
from .v23_candidates import (
    MODEL_PARAMETERS, choose_conservative_rule, collect_v23_splits,
    day_coverage, partition_training, inner_cutoff,
    predictions_for, score, validation_segments,
)
from .v2_research import FEATURE_NAMES_V2

CHANGE_THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90)
RESIDUAL_MAGNITUDE_THRESHOLDS = (0.0, 0.5, 1.0, 2.0)
TREND_MAGNITUDE_THRESHOLDS = (0.0, 0.5, 1.0, 2.0)
CORRECTION_MULTIPLIERS = (0.25, 0.5, 0.75, 1.0)
MAX_TREND_BIKES = 4.0


def _physical(ex: Example, proposed: float) -> float:
    capacity = float(ex.values[2])
    if not math.isfinite(capacity) or capacity <= 0:
        raise ValueError("Qualified example required: capacity unknown")
    return max(0.0, min(capacity, float(proposed)))


def _predictive_delta(ex: Example) -> float:
    """Simple observed movement ONLY from T and the observed past.

    Preference: T-30; otherwise T-15, then T-5. Rescale shorter windows
    to the 30-min horizon, capped to prevent wild extrapolations. The result
    is a prediction feature, not a future label.
    """
    bikes_now = float(ex.values[0])
    for index, factor in ((17, 1.0), (7, 2.0), (6, 6.0)):
        previous = ex.values[index]
        if math.isfinite(previous):
            change = (bikes_now - float(previous)) * factor
            return max(-MAX_TREND_BIKES, min(MAX_TREND_BIKES, change))
    return 0.0


def _trend_prediction(ex: Example, signal: float, *,
                      alpha: float, minimum_signal: float) -> float:
    if alpha <= 0 or abs(signal) <= minimum_signal:
        return float(ex.values[0])
    return _physical(ex, float(ex.values[0]) + alpha * signal)


def _gated_prediction(ex: Example, residual: float, probability: float, *,
                      alpha: float, probability_cutoff: float,
                      minimum_correction: float) -> float:
    if not 0 <= probability <= 1:
        raise ValueError("Invalid probability from change-classifier")
    if alpha <= 0 or probability < probability_cutoff or abs(residual) <= minimum_correction:
        return float(ex.values[0])
    return _physical(ex, float(ex.values[0]) + alpha * residual)


def _raw_mae(examples: Sequence[Example], preds: Sequence[float]) -> float:
    if not examples or len(examples) != len(preds):
        raise ValueError("Need nonempty aligned predictions for calibration")
    return sum(abs(ex.target_bikes - pred) for ex, pred in zip(examples, preds)) / len(examples)


def _chosen_rule(examples: Sequence[Example], proposed_rules: Sequence[tuple],
                 predictor: Callable[[Example, tuple, int], float]) -> dict:
    """Tune on inner TRAIN calibration only, with exact (unrounded) MAE.

    The first candidate is always the zero-correction fallback; near-ties
    prefer fewer changes and ultimately the zero-correction candidate.
    """
    if not examples:
        raise ValueError("No inner training calibration examples")
    baseline = [float(ex.values[0]) for ex in examples]
    baseline_mae = _raw_mae(examples, baseline)
    best_rule = proposed_rules[0]
    best_mae = baseline_mae
    best_changes = 0
    for rule in proposed_rules[1:]:
        preds = [predictor(ex, rule, i) for i, ex in enumerate(examples)]
        mae = _raw_mae(examples, preds)
        changed = sum(abs(p - b) > 1e-10 for p, b in zip(preds, baseline))
        if (mae < best_mae - 1e-10
                or (abs(mae - best_mae) <= 1e-10 and changed < best_changes)):
            best_rule, best_mae, best_changes = rule, mae, changed
    return {
        "parameter_tuple": list(best_rule),
        "baseline_calibration_mae": round(baseline_mae, 5),
        "selected_calibration_mae": round(best_mae, 5),
        "selected_calibration_change_share": round(best_changes / len(examples), 5),
        "tuned_only_on_past_train_calibration": True,
        "grid_size": len(proposed_rules),
    }


def select_trend_rule(calibration: Sequence[Example]) -> dict:
    signals = [_predictive_delta(x) for x in calibration]
    rules = [(0.0, 0.0)] + [
        (alpha, minimum) for alpha in CORRECTION_MULTIPLIERS
        for minimum in TREND_MAGNITUDE_THRESHOLDS
    ]
    return _chosen_rule(
        calibration, rules,
        lambda ex, rule, i: _trend_prediction(
            ex, signals[i], alpha=rule[0], minimum_signal=rule[1]
        ),
    )


def select_gated_rule(calibration: Sequence[Example],
                      predicted_residuals: Sequence[float],
                      probabilities: Sequence[float]) -> dict:
    if len(calibration) != len(predicted_residuals) or len(calibration) != len(probabilities):
        raise ValueError("Classifier and residual predictions must be aligned")
    rules = [(0.0, 1.0, 0.0)] + [
        (alpha, p, magnitude) for alpha in (0.5, 1.0)
        for p in CHANGE_THRESHOLDS for magnitude in RESIDUAL_MAGNITUDE_THRESHOLDS
    ]
    return _chosen_rule(
        calibration, rules,
        lambda ex, rule, i: _gated_prediction(
            ex, float(predicted_residuals[i]), float(probabilities[i]),
            alpha=rule[0], probability_cutoff=rule[1],
            minimum_correction=rule[2],
        ),
    )


def _change_probabilities(classifier, projected_values: Sequence) -> list[float]:
    """Probability of change, not probability of finding a bicycle."""
    if classifier is None:
        return [0.0] * len(projected_values)
    classes = list(classifier.classes_)
    if classes != [0, 1]:
        raise ValueError("Unexpected classifier label encoding")
    return [float(row[1]) for row in classifier.predict_proba(projected_values)]


def compare_stability_methods(train: list[Example], validation: list[Example],
                              captures: Sequence, *, min_core: int = 5000,
                              min_calibration: int = 1000,
                              min_validation: int = 1000) -> dict:
    """Full V2.3.1 scientific scorecard; old test samples never passed/read."""
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

    boundary, test_start = split_limits(captures)
    if any(x.feature_at >= boundary or x.target_at >= boundary for x in train):
        raise ValueError("Train contains later labels/observations")
    if any(x.feature_at < boundary or x.feature_at >= test_start
           or x.target_at >= test_start for x in validation):
        raise ValueError("Validation outside its chronologically purged interval")
    core, calibration = partition_training(train, inner_cutoff(captures, boundary))
    if len(core) < min_core or len(calibration) < min_calibration or len(validation) < min_validation:
        return {
            "status": "insufficient_labeled_pairs",
            "core": len(core), "calibration": len(calibration), "validation": len(validation),
        }
    for label, samples in (("core", core), ("calibration", calibration), ("validation", validation)):
        for ex in samples:
            if len(ex.values) != len(FEATURE_NAMES_V2):
                raise ValueError("V2 feature schema drift in " + label)
            if not (math.isfinite(ex.values[0]) and math.isfinite(ex.values[2])
                    and math.isfinite(ex.target_bikes)):
                raise ValueError("Missing qualified observation/label in " + label)

    # Prevent scikit-learn's histogram binning from receiving a column that
    # contains NO observations in the training period. Do not fill with zeros,
    # and never decide columns using calibration/validation/future data.
    used_columns = [
        index for index in range(len(FEATURE_NAMES_V2))
        if any(math.isfinite(row.values[index]) for row in core)
    ]
    if not used_columns:
        raise ValueError("No observed past-only features in training core")
    excluded_names = [
        feature for index, feature in enumerate(FEATURE_NAMES_V2)
        if index not in used_columns
    ]

    def project(examples):
        return [[row.values[index] for index in used_columns] for row in examples]

    x_core = project(core)
    x_calibration = project(calibration)
    x_validation = project(validation)
    residual = HistGradientBoostingRegressor(**MODEL_PARAMETERS)
    residual.fit(
        x_core,
        [float(x.target_bikes - x.values[0]) for x in core],
    )
    stable_count = sum(x.target_bikes == x.values[0] for x in core)
    change_targets = [int(x.target_bikes != x.values[0]) for x in core]
    classifier = None
    if len(set(change_targets)) == 2:
        classifier = HistGradientBoostingClassifier(
            max_iter=90, max_leaf_nodes=18, max_depth=4, min_samples_leaf=50,
            learning_rate=0.06, l2_regularization=8.0,
            early_stopping=False, random_state=43,
        )
        classifier.fit(x_core, change_targets)

    calibration_residuals = residual.predict(x_calibration)
    validation_residuals = residual.predict(x_validation)
    calibration_probs = _change_probabilities(classifier, x_calibration)
    validation_probs = _change_probabilities(classifier, x_validation)

    trend_rule = select_trend_rule(calibration)
    gated_rule = select_gated_rule(calibration, calibration_residuals, calibration_probs)
    earlier_conservative = choose_conservative_rule(calibration, calibration_residuals)

    t_alpha, t_floor = trend_rule["parameter_tuple"]
    g_alpha, g_probability, g_magnitude = gated_rule["parameter_tuple"]
    validation_predictions = {
        "persistence": [float(x.values[0]) for x in validation],
        "residual_ml": predictions_for(validation, validation_residuals, alpha=1.0, threshold=0.0),
        "v23_conservative": predictions_for(
            validation, validation_residuals,
            alpha=earlier_conservative["alpha"],
            threshold=earlier_conservative["minimum_absolute_correction_bikes"],
        ),
        "simple_bounded_trend": [
            _trend_prediction(x, _predictive_delta(x), alpha=t_alpha, minimum_signal=t_floor)
            for x in validation
        ],
        "classified_stability_gate": [
            _gated_prediction(
                x, float(d), float(p), alpha=g_alpha, probability_cutoff=g_probability,
                minimum_correction=g_magnitude,
            )
            for x, d, p in zip(validation, validation_residuals, validation_probs)
        ],
    }
    results = {name: score(validation, preds)
               for name, preds in validation_predictions.items()}
    baseline_mae = results["persistence"]["mae"]
    for name, value in results.items():
        if name != "persistence":
            value["mae_gain_vs_persistence"] = (
                round(1 - value["mae"] / baseline_mae, 5) if baseline_mae else None
            )
    return {
        "status": "research_comparison_only_no_promoted_model",
        "core_train_rows": len(core),
        "calibration_rows": len(calibration),
        "historical_validation_rows": len(validation),
        "fit_time_stable_ratio": round(stable_count / len(core), 4),
        "change_classifier_fitted": classifier is not None,
        "feature_projection_selected_only_on_train_core": True,
        "features_used_count": len(used_columns),
        "all_missing_training_features_excluded": excluded_names,
        "rule_selection": {
            "trend": trend_rule,
            "change_gate": gated_rule,
            "previous_residual_conservative": earlier_conservative,
        },
        "historical_validation": results,
        "historical_validation_day_coverage": day_coverage(validation),
        "descriptive_only_post_outcome_segments": validation_segments(
            validation, validation_predictions
        ),
        "selection_only_used_training_calibration": True,
        "historical_validation_not_untouched_future_test": True,
        "old_p5_test_block_never_loaded": True,
        "new_future_test_required_for_v24": True,
        "safe_to_publish_forecasts": False,
        "model_exported": False,
        "forecast_exported": False,
    }
