"""All samples here are artificial UNIT TEST fixtures, never ML validation."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from urban_ops.p5 import Example, Observation, features_for
from urban_ops.v2_research import (
    ADDED_NAMES, FEATURE_NAMES_V2, collect_v2_splits, features_v2_for,
    stream_v2_examples,
)
from scripts.v2_diagnose import feature_coverage, group_summary, run, validation_segments

T = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)


def obs(minute: int, bikes=5, *, station=101, usable=True):
    return Observation(
        station_id=station, at=T + timedelta(minutes=minute), bikes=bikes,
        docks=20 - bikes, capacity=20, mechanical=bikes, electric=0,
        report_lag_seconds=30, latitude=48.87, longitude=2.33, usable=usable,
    )


def test_v2_past_only_features_are_in_addition_to_unchanged_v1():
    history = deque([obs(-30, 10), obs(-15, 8), obs(-10, 7), obs(-5, 6)])
    now = obs(0, 5)
    actual = features_v2_for(now, history)
    existing = features_for(now, history)
    assert actual is not None and existing is not None
    assert actual.values[:len(existing.values)] == existing.values
    assert len(actual.values) == len(FEATURE_NAMES_V2) == 16 + len(ADDED_NAMES)
    assert actual.values[16] == 7  # real -10m
    assert actual.values[17] == 10  # real -30m
    assert actual.values[18] == -5  # observed difference, not a future label
    assert actual.values[19] == 0.25
    assert actual.values[20] == 0.75
    assert actual.values[21] == 4
    assert actual.values[23] == 5  # most recent qualified history


def test_v2_unavailable_lags_stay_nan_without_interpolation():
    now = features_v2_for(obs(0), deque([obs(-24, 8)]))
    assert math.isnan(now.values[16]) and math.isnan(now.values[17])
    assert math.isnan(now.values[18])
    assert now.values[21] == 1


def test_v2_rejects_current_future_and_other_station_in_history():
    with pytest.raises(ValueError, match="Cross-station/current/future"):
        features_v2_for(obs(0), deque([obs(0)]))
    with pytest.raises(ValueError, match="Cross-station/current/future"):
        features_v2_for(obs(0), deque([obs(5)]))
    with pytest.raises(ValueError, match="Cross-station/current/future"):
        features_v2_for(obs(0), deque([obs(-5, station=202)]))


def test_v2_does_not_use_unusable_observations_as_features_or_labels():
    observations = [obs(i * 5, bikes=4 + i, usable=i != 6) for i in range(8)]
    output = list(stream_v2_examples(observations))
    labels = [ex for _, ex in output if ex is not None]
    assert len(labels) == 1
    assert labels[0].feature_at == T + timedelta(minutes=5)
    assert labels[0].target_at == T + timedelta(minutes=35)
    assert all(ex.target_at != T + timedelta(minutes=30) for ex in labels)
    assert all(cand.feature_at != T + timedelta(minutes=30)
               for cand, _ in output if cand is not None)


def test_duplicate_captures_cannot_add_new_training_pairs():
    inputs = [obs(i * 5) for i in range(8)]
    doubled = inputs[:2] + [inputs[2], inputs[2]] + inputs[3:]
    assert len([x for _, x in stream_v2_examples(doubled) if x]) == 2


def test_v2_splits_purge_cross_boundary_labels():
    inputs = [obs(i * 30) for i in range(8 * 48 + 1)]
    samples, (v, t) = collect_v2_splits(inputs, [x.at for x in inputs])
    assert all(ex.target_at < v for ex in samples["train"].items)
    assert all(v <= ex.feature_at < t and ex.target_at < t
               for ex in samples["validation"].items)
    assert all(ex.feature_at >= t for ex in samples["test"].items)
    assert all(len(ex.values) == len(FEATURE_NAMES_V2)
               for name in samples for ex in samples[name].items)


def test_validation_segments_are_descriptive_not_model_selection():
    records = [
        Example(101, T + timedelta(minutes=5 * i),
                T + timedelta(minutes=30 + 5 * i),
                (float(i % 4), 10., 20., 0., 0., 60.,
                 math.nan, math.nan) + (math.nan,) * 8,
                float((i + 1) % 4))
        for i in range(120)
    ]
    predictions = [float(i % 4) for i in range(120)]
    groups = validation_segments(records, predictions)
    assert groups["validation_samples_examined"] == 120
    assert sum(g["samples"] for g in groups["change_size"].values()) == 120
    assert "history_5m" in groups
    assert "test" not in groups


def test_group_below_threshold_is_suppressed():
    assert group_summary([(5, 5, 6)]) == {"samples": 1, "suppressed": True}
    assert group_summary([(5, 5, 6)], minimum=0)["incumbent_minus_baseline_mae"] == 1.0


def test_not_ready_v2_diagnostic_cannot_create_model_or_forecast(tmp_path):
    db = tmp_path / "fixture.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE ingestion_runs(run_id TEXT,started_at TEXT,status TEXT)")
        conn.execute("INSERT INTO ingestion_runs VALUES (?,?,?)", ("fixture-only", T.isoformat(), "success"))
    evidence = tmp_path / "fixture-replay.json"
    evidence.write_text(json.dumps([
        {"run_id": "fixture-only", "status": "success", "asset": "fixture-unit-test.tar.gz"},
    ]), encoding="utf-8")
    output = tmp_path / "diagnostics"
    result = run("sqlite:///" + str(db), evidence, output)
    assert result["status"] == "not_ready"
    assert result["safe_to_publish_forecasts"] is False
    assert sorted(p.name for p in output.iterdir()) == ["V2_1_V2_2_DIAGNOSTICS.json"]
