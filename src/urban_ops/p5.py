"""P5: leakage-resistant Vélib' availability forecasting from qualified P3 snapshots.

Target: observed bikes at a station ~30 minutes after a known capture. This is
NOT demand, traffic or a prediction of individual riders. No interpolation or
synthetic labels are used; missing future observations do not create training rows.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path
from typing import Iterable, Iterator
from zoneinfo import ZoneInfo

from sqlalchemy import text

PARIS = ZoneInfo("Europe/Paris")
HORIZON = timedelta(minutes=30)
TOLERANCE = timedelta(minutes=2)
FEATURE_NAMES = (
    "bikes_now", "docks_now", "capacity", "mechanical_now", "electric_now",
    "report_lag_seconds", "bikes_5m_ago", "bikes_15m_ago", "delta_5m", "delta_15m",
    "local_time_sin", "local_time_cos", "weekday_sin", "weekday_cos",
    "latitude", "longitude",
)


def utc(value: datetime | str) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Capture timestamp without timezone")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Observation:
    station_id: int
    at: datetime
    bikes: int | None
    docks: int | None
    capacity: int
    mechanical: int | None = None
    electric: int | None = None
    report_lag_seconds: int | None = None
    latitude: float = 0.0
    longitude: float = 0.0
    usable: bool = True


@dataclass(frozen=True)
class Features:
    station_id: int
    feature_at: datetime
    capacity: int
    values: tuple[float, ...]


@dataclass(frozen=True)
class Example:
    station_id: int
    feature_at: datetime
    target_at: datetime
    values: tuple[float, ...]
    target_bikes: float


def _usable(obs: Observation) -> bool:
    return (obs.usable and obs.capacity > 0 and obs.bikes is not None and
            obs.docks is not None and 0 <= obs.bikes <= obs.capacity and
            0 <= obs.docks <= obs.capacity and obs.bikes + obs.docks <= obs.capacity)


def features_for(obs: Observation, prior: deque[Observation]) -> Features | None:
    """Only looks at past data; history is never allowed to contain the future."""
    if not _usable(obs):
        return None

    def lag(minutes: int) -> float:
        expected = utc(obs.at) - timedelta(minutes=minutes)
        options = [o for o in prior if _usable(o) and o.at < obs.at and
                   abs((o.at - expected).total_seconds()) <= TOLERANCE.total_seconds()]
        return float(min(options, key=lambda o: abs((o.at - expected).total_seconds())).bikes) if options else math.nan

    lag5, lag15 = lag(5), lag(15)
    local = utc(obs.at).astimezone(PARIS)
    minute = (local.hour * 60 + local.minute + local.second / 60) / 1440
    weekday = local.weekday() / 7
    delta5 = float(obs.bikes) - lag5 if math.isfinite(lag5) else math.nan
    delta15 = float(obs.bikes) - lag15 if math.isfinite(lag15) else math.nan
    vals = (
        float(obs.bikes), float(obs.docks), float(obs.capacity),
        float(obs.mechanical) if obs.mechanical is not None else math.nan,
        float(obs.electric) if obs.electric is not None else math.nan,
        float(obs.report_lag_seconds) if obs.report_lag_seconds is not None else math.nan,
        lag5, lag15, delta5, delta15,
        math.sin(2 * math.pi * minute), math.cos(2 * math.pi * minute),
        math.sin(2 * math.pi * weekday), math.cos(2 * math.pi * weekday),
        float(obs.latitude), float(obs.longitude),
    )
    assert len(vals) == len(FEATURE_NAMES)
    return Features(obs.station_id, utc(obs.at), obs.capacity, vals)


def examples_and_latest(observations: Iterable[Observation]) -> tuple[list[Example], dict[int, Features]]:
    """For small fixture tests only. Use stream_examples for real large histories."""
    newest = {}
    examples = []
    for candidate, result in stream_examples(observations):
        if candidate is not None:
            newest[candidate.station_id] = candidate
        if result is not None:
            examples.append(result)
    return examples, newest


def stream_examples(observations: Iterable[Observation]) -> Iterator[tuple[Features | None, Example | None]]:
    """Requires station_id/UTC sorted source; O(stations x ~30min) RAM.

    Yields (features_for_current_capture, completed_label_for_past_capture).
    A target must itself be qualified, must really exist in the DB and must
    land within 30min +/-2min. No random train/test split, no forward filling.
    """
    for sid, station in groupby(observations, key=lambda row: row.station_id):
        prior: deque[Observation] = deque()
        pending: deque[Features] = deque()
        last = None
        for raw in station:
            o = Observation(**{**raw.__dict__, "at": utc(raw.at)})
            if last is not None and o.at < last:
                raise ValueError(f"Unsorted observations at station {sid}")
            if last is not None and o.at == last:
                # Duplicate capture timestamp: never count twice as separate labels.
                continue
            last = o.at
            while prior and (o.at - prior[0].at) > timedelta(minutes=18):
                prior.popleft()
            while pending and o.at - pending[0].feature_at > HORIZON + TOLERANCE:
                pending.popleft()
            if _usable(o):
                for old in list(pending):
                    if abs((o.at - old.feature_at - HORIZON).total_seconds()) <= TOLERANCE.total_seconds():
                        pending.remove(old)
                        yield None, Example(sid, old.feature_at, o.at, old.values, float(o.bikes))
            feat = features_for(o, prior)
            if feat is not None:
                yield feat, None
                pending.append(feat)
            prior.append(o)


def sql_observations(database_url: str) -> Iterator[Observation]:
    """Streaming SQLite/Postgres reader. Reuses P3 is_usable quality gate."""
    from .storage import make_engine
    engine = make_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execution_options(yield_per=5000).execute(text("""
                SELECT f.station_id, f.collected_at, f.num_bikes_available,
                       f.num_docks_available, f.mechanical_bikes, f.electric_bikes,
                       f.reported_lag_seconds, f.is_usable,
                       s.capacity, s.latitude, s.longitude
                FROM fact_station_status f
                JOIN ingestion_runs r ON r.run_id=f.run_id AND r.status='success'
                JOIN dim_stations s ON s.station_id=f.station_id
                ORDER BY f.station_id, f.collected_at, f.id
            """))
            for r in rows.mappings():
                yield Observation(
                    station_id=int(r["station_id"]), at=utc(r["collected_at"]),
                    bikes=r["num_bikes_available"], docks=r["num_docks_available"],
                    mechanical=r["mechanical_bikes"], electric=r["electric_bikes"],
                    report_lag_seconds=r["reported_lag_seconds"], usable=bool(r["is_usable"]),
                    capacity=int(r["capacity"]), latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                )
    finally:
        engine.dispose()


def successful_captures(database_url: str) -> list[datetime]:
    from .storage import make_engine
    engine = make_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT started_at FROM ingestion_runs WHERE status='success' ORDER BY started_at"))
            return sorted({utc(row[0]) for row in rows})
    finally:
        engine.dispose()


def readiness(captures: Iterable[datetime], *, min_days: int = 7,
              min_captures: int = 900, min_coverage: float = 0.40) -> dict:
    """Explicit gate: one or a few captures can never masquerade as ML proof."""
    times = sorted({utc(t) for t in captures})
    if not times:
        return {"ready": False, "reason": "no_real_captures", "captures": 0,
                "distinct_5m_slots": 0, "repeated_5m_slot_captures": 0,
                "expected_5m_slots": None, "remaining_captures_to_min": min_captures,
                "hours_to_minimum_span": None, "earliest_span_eligibility_utc": None,
                "span_days": 0.0, "coverage_estimate": None,
                "from_utc": None, "through_utc": None}
    days = (times[-1] - times[0]).total_seconds() / 86400
    # A run may archive multiple observations in the same five-minute UTC
    # window. Only one such observation can establish interval coverage.
    # This is a *metadata* preflight; replay SHA and station is_usable gates
    # remain mandatory in the subsequent stage.
    distinct_slots = len({int(t.timestamp()) // 300 for t in times})
    slots = (int(times[-1].timestamp()) // 300
             - int(times[0].timestamp()) // 300 + 1)
    coverage = min(1.0, distinct_slots / slots) if len(times) > 1 else None
    ready = days >= min_days and len(times) >= min_captures and coverage is not None and coverage >= min_coverage
    if days < min_days:
        reason = "insufficient_calendar_span"
    elif len(times) < min_captures:
        reason = "insufficient_captures"
    elif coverage is None or coverage < min_coverage:
        reason = "insufficient_capture_coverage"
    else:
        reason = "ready"
    return {"ready": ready, "reason": reason, "captures": len(times),
            "distinct_5m_slots": distinct_slots,
            "repeated_5m_slot_captures": len(times) - distinct_slots,
            "expected_5m_slots": slots,
            "remaining_captures_to_min": max(0, min_captures - len(times)),
            "hours_to_minimum_span": round(max(0.0, 24 * (min_days - days)), 2),
            "span_days": round(days, 3), "coverage_estimate": round(coverage, 4) if coverage is not None else None,
            "earliest_span_eligibility_utc": (times[0] + timedelta(days=min_days)).isoformat(),
            "from_utc": times[0].isoformat(), "through_utc": times[-1].isoformat()}


class Reservoir:
    """Bounded reproducible sample from each *chronological* split."""
    def __init__(self, limit: int, seed: int):
        self.limit = limit
        self.rng = random.Random(seed)
        self.seen = 0
        self.items: list[Example] = []

    def add(self, item: Example) -> None:
        self.seen += 1
        if len(self.items) < self.limit:
            self.items.append(item)
        else:
            index = self.rng.randrange(self.seen)
            if index < self.limit:
                self.items[index] = item


def split_limits(captures: Iterable[datetime]) -> tuple[datetime, datetime]:
    times = sorted({utc(t) for t in captures})
    if len(times) < 3:
        raise ValueError("At least 3 distinct captures required")
    first, last = times[0], times[-1]
    span = last - first
    return first + span * 0.60, first + span * 0.80


def collect_splits(observations: Iterable[Observation], capture_times: Iterable[datetime],
                   max_train: int = 100_000, max_eval: int = 25_000):
    """Purged chronological train/validation/test, no future labels at split cutoffs."""
    validation_start, test_start = split_limits(capture_times)
    sets = {"train": Reservoir(max_train, 11), "validation": Reservoir(max_eval, 12),
            "test": Reservoir(max_eval, 13)}
    last_features = {}
    for current, ex in stream_examples(observations):
        if current is not None:
            last_features[current.station_id] = current
        if ex is None:
            continue
        if ex.feature_at < validation_start and ex.target_at < validation_start:
            sets["train"].add(ex)
        elif validation_start <= ex.feature_at < test_start and ex.target_at < test_start:
            sets["validation"].add(ex)
        elif ex.feature_at >= test_start:
            sets["test"].add(ex)
        # Samples crossing a temporal boundary are intentionally purged.
    return sets, last_features, (validation_start, test_start)


def mae(truth: list[float], predicted: list[float]) -> float:
    if len(truth) != len(predicted) or not truth:
        raise ValueError("Need paired non-empty observations")
    return sum(abs(a-b) for a,b in zip(truth,predicted)) / len(truth)


def rmse(truth: list[float], predicted: list[float]) -> float:
    if len(truth) != len(predicted) or not truth:
        raise ValueError("Need paired non-empty observations")
    return math.sqrt(sum((a-b)**2 for a,b in zip(truth,predicted)) / len(truth))


def bounded(values, examples: list[Example]) -> list[float]:
    return [max(0.0, min(float(ex.values[2]), float(y))) for ex,y in zip(examples,values)]


def evaluate(model, examples: list[Example]) -> dict:
    y = [x.target_bikes for x in examples]
    baseline = [x.values[0] for x in examples]
    ml = bounded(model.predict([x.values for x in examples]), examples)
    baseline_mae, ml_mae = mae(y,baseline), mae(y,ml)
    return {"n": len(examples), "persistence_mae": round(baseline_mae, 4),
            "persistence_rmse": round(rmse(y,baseline), 4),
            "ml_mae": round(ml_mae,4), "ml_rmse": round(rmse(y,ml),4),
            "mae_skill_vs_persistence": round(1-ml_mae/baseline_mae,4) if baseline_mae else None}


def fit_and_score(sets: dict, *, min_train: int = 5000, min_eval: int = 1000) -> tuple[object | None, dict]:
    counts = {k: {"sampled": len(v.items), "eligible": v.seen} for k,v in sets.items()}
    if counts["train"]["sampled"] < min_train or any(counts[k]["sampled"] < min_eval for k in ("validation", "test")):
        return None, {"status": "insufficient_labeled_pairs", "splits": counts}
    # sklearn deliberately loaded only after sufficient real training labels exist.
    from sklearn.ensemble import HistGradientBoostingRegressor
    train = sets["train"].items
    model = HistGradientBoostingRegressor(max_iter=120, max_leaf_nodes=24, max_depth=5,
                                          min_samples_leaf=40, learning_rate=0.08,
                                          l2_regularization=5.0, random_state=42)
    model.fit([x.values for x in train], [x.target_bikes for x in train])
    validation = evaluate(model, sets["validation"].items)
    holdout = evaluate(model, sets["test"].items)
    val_skill = validation["mae_skill_vs_persistence"]
    test_skill = holdout["mae_skill_vs_persistence"]
    # Candidate qualifies only if it beats naive persistence BOTH in validation
    # and completely untouched held-out test period.
    promoted = val_skill is not None and val_skill >= 0.01 and test_skill is not None and test_skill > 0
    return (model if promoted else None), {
        "status": "validated_model" if promoted else "baseline_wins_or_uncertain",
        "splits": counts, "validation": validation, "holdout": holdout,
        "selection_rule": "ML validation MAE >=1% better than persistence AND holdout MAE strictly better",
        "candidate": "HistGradientBoostingRegressor", "baseline": "persistence_bikes_now",
    }