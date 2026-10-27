"""V2.2 experimental, strictly historical features, independent of production P5.

Never deploy this module or use it for published forecasts without separate V2
validation. Features use only the current *qualified* P3 observation and prior
qualified observations from the same station. Missing lags remain NaN.
"""
from __future__ import annotations

import math
from collections import deque
from datetime import timedelta
from itertools import groupby
from typing import Iterable, Iterator

from .p5 import (
    Example, Features, HORIZON, TOLERANCE, Observation, Reservoir, _usable,
    features_for, split_limits, utc, FEATURE_NAMES,
)

ADDED_NAMES = (
    "bikes_10m_ago",
    "bikes_30m_ago",
    "delta_30m",
    "bikes_fraction_of_capacity",
    "docks_fraction_of_capacity",
    "qualified_history_30m_count",
    "qualified_history_30m_volatility",
    "minutes_since_prior_qualified",
    "qualified_history_30m_range",
)
FEATURE_NAMES_V2 = FEATURE_NAMES + ADDED_NAMES
PAST_WINDOW = timedelta(minutes=33)


def features_v2_for(obs: Observation, prior: Iterable[Observation]) -> Features | None:
    """Compute an *experimental* vector without time travel or fabricated history.

    The caller is responsible for station grouping. Validate that no supplied
    prior comes from this capture's instant or its future before computing.
    """
    observations = list(prior)
    current_at = utc(obs.at)
    for row in observations:
        if row.station_id != obs.station_id or utc(row.at) >= current_at:
            raise ValueError("Cross-station/current/future observation in V2 feature history")
    original = features_for(obs, deque(observations))
    if original is None:
        return None
    available = [
        row for row in observations
        if _usable(row) and (current_at - utc(row.at)) <= PAST_WINDOW
    ]

    def lag(minutes: int) -> float:
        wanted = current_at - timedelta(minutes=minutes)
        candidates = [
            row for row in available
            if abs((utc(row.at) - wanted).total_seconds()) <= TOLERANCE.total_seconds()
        ]
        if not candidates:
            return math.nan
        chosen = min(candidates, key=lambda row: abs((utc(row.at) - wanted).total_seconds()))
        return float(chosen.bikes)

    bikes10 = lag(10)
    bikes30 = lag(30)
    recent = [
        float(row.bikes) for row in available
        if current_at - utc(row.at) <= timedelta(minutes=30)
    ]
    recent.append(float(obs.bikes))
    avg = sum(recent) / len(recent)
    volatility = math.sqrt(sum((v - avg)**2 for v in recent) / len(recent))
    minutes_since = (
        (current_at - max(utc(row.at) for row in available)).total_seconds() / 60
        if available else math.nan
    )
    extra = (
        bikes10,
        bikes30,
        float(obs.bikes) - bikes30 if math.isfinite(bikes30) else math.nan,
        float(obs.bikes) / obs.capacity,
        float(obs.docks) / obs.capacity,
        float(len(recent) - 1),
        volatility,
        minutes_since,
        max(recent) - min(recent),
    )
    assert len(extra) == len(ADDED_NAMES)
    return Features(obs.station_id, current_at, obs.capacity, original.values + extra)


def stream_v2_examples(observations: Iterable[Observation]) -> Iterator[tuple[Features | None, Example | None]]:
    """Station-local UTC stream, using real target captures +30min +/-2min.

    Maintains the same time and quality gate as P5 while leaving P5 untouched.
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
                continue  # duplicate raw instant does not create an example
            last = o.at
            while prior and (o.at - prior[0].at) > PAST_WINDOW:
                prior.popleft()
            while pending and o.at - pending[0].feature_at > HORIZON + TOLERANCE:
                pending.popleft()
            if _usable(o):
                for old in list(pending):
                    if abs((o.at - old.feature_at - HORIZON).total_seconds()) <= TOLERANCE.total_seconds():
                        pending.remove(old)
                        yield None, Example(sid, old.feature_at, o.at, old.values, float(o.bikes))
            candidate = features_v2_for(o, prior)
            if candidate is not None:
                pending.append(candidate)
                yield candidate, None
            prior.append(o)


def collect_v2_splits(
    observations: Iterable[Observation],
    captures: Iterable,
    *,
    max_train: int = 10_000,
    max_eval: int = 5_000,
):
    """Independent V2 feature/readiness audit, no fitting or promotion."""
    validation_start, test_start = split_limits(captures)
    sets = {
        "train": Reservoir(max_train, 21),
        "validation": Reservoir(max_eval, 22),
        "test": Reservoir(max_eval, 23),
    }
    for _, ex in stream_v2_examples(observations):
        if ex is None:
            continue
        if ex.feature_at < validation_start and ex.target_at < validation_start:
            sets["train"].add(ex)
        elif validation_start <= ex.feature_at < test_start and ex.target_at < test_start:
            sets["validation"].add(ex)
        elif ex.feature_at >= test_start:
            sets["test"].add(ex)
    return sets, (validation_start, test_start)
