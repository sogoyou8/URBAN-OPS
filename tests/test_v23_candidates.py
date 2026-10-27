"""Synthetic UNIT TESTS ONLY. They do not establish real model performance."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scripts.train_v23 import run
from urban_ops.p5 import Example, Observation
from urban_ops.v2_research import FEATURE_NAMES_V2
from urban_ops.v23_candidates import (
    clamp, collect_v23_splits, compare_candidates, corrected,
    choose_conservative_rule, inner_cutoff, partition_training,
    predictions_for, score, validation_segments,
)

T = datetime(2026, 10, 18, tzinfo=timezone.utc)


def ex(minute: int, bikes=8, target=8, *, station=101):
    vals = (
        float(bikes), 20.0 - bikes, 20.0,
        float(bikes), 0.0, 30.0,
        float(bikes), float(bikes), 0.0, 0.0,
        0.0, 1.0, 0.0, 1.0, 48.88, 2.35,
        float(bikes), float(bikes), 0.0,
        bikes / 20, (20-bikes) / 20, 6.0, 0.0, 5.0, 0.0
    )
    assert len(vals) == len(FEATURE_NAMES_V2)
    at = T + timedelta(minutes=minute)
    return Example(station, at, at + timedelta(minutes=30), vals, float(target))


def test_physical_bounding_and_conservative_gate_only_use_predicted_delta():
    sample = ex(0,bikes=8,target=10)
    assert clamp(sample, -100.0) == 0.0
    assert clamp(sample, 100.0) == 20.0
    assert corrected(sample, 10.0) == 18.0
    assert corrected(sample, -100.0) == 0.0
    assert corrected(sample, 0.9, alpha=1.0, threshold=1.0) == 8.0
    assert corrected(sample, 2.0, alpha=0.5, threshold=1.0) == 9.0
    assert corrected(sample, 999, alpha=0.0) == 8.0


def test_conservative_rule_can_refuse_all_false_adjustments():
    calibration = [ex(i*5, bikes=7, target=7) for i in range(130)]
    rule = choose_conservative_rule(calibration, [2.5] * len(calibration))
    assert rule["alpha"] == 0.0
    assert rule["chosen_calibration"]["mae"] == 0
    assert rule["grid_size"] == 21
    assert rule["selection_only_used_internal_training_calibration"]


def test_score_is_aligned_and_never_reports_fake_accuracy():
    samples = [ex(0,bikes=6,target=7), ex(5,bikes=6,target=6)]
    report = score(samples, [6,6])
    assert report["pairs"] == 2
    assert report["mae"] == 0.5
    with pytest.raises(ValueError, match="aligned"):
        predictions_for(samples, [1.0],alpha=1.0,threshold=0)


def test_training_internal_calibration_is_temporally_purged():
    captures = [T,T+timedelta(days=1),T+timedelta(days=10)]
    outer_val = T + timedelta(days=6)
    cutoff = inner_cutoff(captures,outer_val)
    train = [ex(i*30) for i in range(6*48)]
    core,calibration=partition_training(train,cutoff)
    assert core and calibration
    assert all(x.target_at < cutoff for x in core)
    assert all(x.feature_at >= cutoff for x in calibration)
    assert len(core)+len(calibration) < len(train)  # label purge


def test_v23_collects_no_old_test_block_and_purges_boundaries():
    readings = [
        Observation(101,T+timedelta(minutes=5*i),7,13,20,usable=True)
        for i in range(10*24*12+1)
    ]
    splits, (val,test) = collect_v23_splits(readings,
        [r.at for r in readings], max_train=400,max_validation=200)
    assert set(splits) == {"train","validation"}
    assert splits["train"].seen > 0 and splits["validation"].seen > 0
    assert all(x.target_at < val for x in splits["train"].items)
    assert all(val <= x.feature_at and x.target_at < test
               for x in splits["validation"].items)


def test_residual_and_conservative_comparison_never_queries_old_test():
    pytest.importorskip("sklearn")
    captures=[T,T+timedelta(days=1),T+timedelta(days=10)]
    train=[
        ex(i*5,bikes=4+(i%12),target=4+(i%12))
        for i in range(6*24*12-8)
    ]
    validation=[
        ex(6*24*60+i*5,bikes=4+(i%12),target=4+(i%12))
        for i in range(145)
    ]
    result=compare_candidates(train,validation,captures,
                              min_core=150,min_calibration=100,min_validation=100)
    assert result["status"]=="compared_on_existing_validation_only"
    assert set(result["outer_validation"]) == {
        "persistence","residual_ml","conservative_residual"
    }
    assert result["outer_validation"]["persistence"]["mae"] == 0.0
    assert result["no_old_test_evaluated"]
    assert not result["safe_to_publish_forecasts"]
    assert not result["model_saved"]
    assert result["internal_calibration_rule"]["selection_only_used_internal_training_calibration"]
    assert result["outer_validation_post_outcome_segments"]["truly_unchanged"]["persistence"]["mae"]==0


def test_rejects_data_from_test_or_validation_in_train():
    captures=[T,T+timedelta(days=1),T+timedelta(days=10)]
    with pytest.raises(ValueError,match="Training contains"):
        compare_candidates([ex(6*24*60)], [ex(6*24*60+60)], captures,
                           min_core=1,min_calibration=1,min_validation=1)


def test_cli_blocks_thin_history_and_never_exports_model(tmp_path):
    db=tmp_path/"tiny.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE ingestion_runs(run_id TEXT,started_at TEXT,status TEXT)")
        con.execute("INSERT INTO ingestion_runs VALUES (?,?,?)",("fixture",T.isoformat(),"success"))
    evidence=tmp_path/"verified-unit-test-only.json"
    evidence.write_text(json.dumps([
        {"run_id":"fixture","asset":"synthetic-fixture.tar.gz","status":"success"},
    ]),encoding="utf-8")
    output=tmp_path/"research"
    report=run("sqlite:///"+str(db),evidence,output)
    assert report["status"]=="not_ready"
    assert report["safe_to_publish_forecasts"] is False
    assert [p.name for p in output.iterdir()] == ["V2_3_RESEARCH_COMPARISON.json"]
    (output/"model.joblib").write_bytes(b"fixture")
    with pytest.raises(ValueError,match="cannot contain models"):
        run("sqlite:///"+str(db),evidence,output)
