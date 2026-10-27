"""V2.4 pre-registered protocol, immutable temporal cutoffs and evidence gates.

All times UTC. There is NO automatic model promotion or production path.
The challenger is the original residual ML candidate with frozen V2.3
hyperparameters; this candidate has NOT beaten the historical baseline and
is therefore not eligible for deployment, regardless of new-test outcomes.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from .p5 import HORIZON, utc

PROTOCOL = {
    "id": "urban-ops-v24-20261027-locked-v1",
    "training_end_exclusive_utc": "2026-10-27T10:40:00+00:00",
    "future_holdout_start_utc": "2026-10-28T00:00:00+00:00",
    "future_holdout_end_exclusive_utc": "2026-11-04T00:00:00+00:00",
    "earliest_evaluation_utc": "2026-11-04T04:00:00+00:00",
    "prediction_horizon_minutes": 30,
    "target_tolerance_minutes": 2,
    "expected_utc_five_minute_slots": 2016,
    "minimum_distinct_slot_coverage": 0.75,
    "minimum_actual_label_pairs": 20000,
    "minimum_actual_pairs_per_utc_day": 1000,
    "minimum_distinct_stations_with_labels": 300,
    "evaluation_sample_cap": 40000,
    "random_seed": 2404,
    "minimum_historical_train_pairs": 5000,
    "historical_train_sample_cap": 90000,
    "historical_challenger_passed_selection_gate": False,
    "promote_model_automatically": False,
    "historical_selection_gate": ">=1% MAE gain on independent historical validation",
    "future_holdout_gate": "strictly positive MAE gain on full future holdout",
    "methods": [
        "persistence_bikes_now",
        "frozen_v23_residual_ml_with_absolute_error_loss_no_tuning",
    ],
}
PROTOCOL_FINGERPRINT = sha256(
    json.dumps(PROTOCOL, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


def dt(key: str) -> datetime:
    return utc(PROTOCOL[key])


def check_static_protocol() -> None:
    a, b, c, d = (
        dt("training_end_exclusive_utc"), dt("future_holdout_start_utc"),
        dt("future_holdout_end_exclusive_utc"), dt("earliest_evaluation_utc"),
    )
    if not (a < b < c <= d) or c - b != timedelta(days=7):
        raise ValueError("Invalid V2.4 temporal preregistration")
    if int((c - b).total_seconds() / 300) != PROTOCOL["expected_utc_five_minute_slots"]:
        raise ValueError("Slot count differs from fixed future window")
    if HORIZON != timedelta(minutes=PROTOCOL["prediction_horizon_minutes"]):
        raise ValueError("Forecast horizon changed in V2.4")


def future_capture_gate(capture_times, evaluated_at: datetime) -> dict:
    """Preflight from genuine successful ingestion timestamps in the frozen window.

    Timestamp inventory is NOT proof of station labels or archive integrity.
    """
    check_static_protocol()
    evaluated_at = utc(evaluated_at)
    start, end = dt("future_holdout_start_utc"), dt("future_holdout_end_exclusive_utc")
    eligible = sorted({utc(t) for t in capture_times if start <= utc(t) < end})
    slots = {int(t.timestamp()) // 300 for t in eligible}
    observed = len(slots)
    total = PROTOCOL["expected_utc_five_minute_slots"]
    coverage = observed / total
    reached_date = evaluated_at >= dt("earliest_evaluation_utc")
    checks = {
        "time_window_ended": reached_date,
        "distinct_5m_slot_coverage_at_least_75pct":
            coverage >= PROTOCOL["minimum_distinct_slot_coverage"],
        "near_start_capture_present":
            bool(eligible and eligible[0] <= start + timedelta(minutes=20)),
        "near_end_capture_present":
            bool(eligible and eligible[-1] >= end - timedelta(minutes=20)),
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "unique_successful_captures_in_window": len(eligible),
        "distinct_5m_slots": observed,
        "expected_5m_slots": total,
        "coverage": round(coverage, 5),
        "start_utc": start.isoformat(),
        "end_exclusive_utc": end.isoformat(),
        "assessed_at_utc": evaluated_at.isoformat(),
        "is_not_real_label_quality_proof": True,
    }


def actual_labels_gate(day_counts: dict[str, int], stations: set[int]) -> dict:
    """All-day counts come from ACTUAL qualified +30m labels, not samples."""
    start, end = dt("future_holdout_start_utc"), dt("future_holdout_end_exclusive_utc")
    days = [(start + timedelta(days=i)).date().isoformat() for i in range(7)]
    observed = {day: int(day_counts.get(day, 0)) for day in days}
    total = sum(observed.values())
    weekdays = sum(observed[day] > 0 for day in days
                   if datetime.fromisoformat(day).weekday() < 5)
    weekends = sum(observed[day] > 0 for day in days
                   if datetime.fromisoformat(day).weekday() >= 5)
    checks = {
        "seven_real_utc_dates_with_1000_labels_each": all(
            count >= PROTOCOL["minimum_actual_pairs_per_utc_day"]
            for count in observed.values()
        ),
        "at_least_five_weekday_dates": weekdays >= 5,
        "at_least_two_weekend_dates": weekends >= 2,
        "minimum_qualified_pairs": total >= PROTOCOL["minimum_actual_label_pairs"],
        "minimum_stations": len(stations) >= PROTOCOL["minimum_distinct_stations_with_labels"],
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "paired_real_observations_total": total,
        "by_utc_date": observed,
        "station_count": len(stations),
        "weekday_dates_with_labels": weekdays,
        "weekend_dates_with_labels": weekends,
        "missing_target_pairs_never_invented": True,
    }


def decision(baseline_mae: float, challenger_mae: float) -> dict:
    """Never infer publication eligibility from a raw future metric alone."""
    if baseline_mae < 0 or challenger_mae < 0:
        raise ValueError("Negative forecast error impossible")
    improvement = ((baseline_mae - challenger_mae) / baseline_mae
                   if baseline_mae > 0 else None)
    historical_gate = bool(PROTOCOL["historical_challenger_passed_selection_gate"])
    future_gate = improvement is not None and improvement > 0
    return {
        "relative_future_mae_improvement": round(improvement, 5)
        if improvement is not None else None,
        "future_gain_positive": future_gate,
        "historical_selection_passed": historical_gate,
        "promotion_eligible": False,  # explicit research-only policy
        "status": (
            "historical_gate_failed_even_if_future_improves"
            if future_gate else "baseline_wins_or_future_gain_not_proven"
        ),
        "new_model_not_authorized_for_public_predictions": True,
    }


check_static_protocol()
