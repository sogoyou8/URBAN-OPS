"""Synthetic-only contracts for V2.3.1; NEVER empirical Vélib' results."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scripts.train_v231 import run
from urban_ops.p5 import Example
from urban_ops.v2_research import FEATURE_NAMES_V2
from urban_ops.v231_stability import (
    _predictive_delta, _gated_prediction, _trend_prediction,
    compare_stability_methods, select_gated_rule, select_trend_rule,
)

T = datetime(2026, 10, 18, tzinfo=timezone.utc)


def example(minute: int, now: int = 8, future: int = 8, *, lag30=math.nan):
    vals = (
        float(now), float(20-now), 20.0, float(now), 0.0, 30.0,
        math.nan, math.nan, math.nan, math.nan,
        0.0, 1.0, 0.0, 1.0, 48.85, 2.35,
        math.nan, lag30,
        float(now-lag30) if math.isfinite(lag30) else math.nan,
        now/20.0, (20-now)/20.0, 0, 0, math.nan, 0,
    )
    assert len(vals) == len(FEATURE_NAMES_V2)
    at = T + timedelta(minutes=minute)
    return Example(101, at, at + timedelta(minutes=30), vals, float(future))


def test_simple_trend_only_uses_available_older_real_bikes():
    moving = example(0,now=12,lag30=10)
    assert _predictive_delta(moving) == 2
    assert _trend_prediction(moving,2,alpha=0.5,minimum_signal=0) == 13
    assert _trend_prediction(moving,2,alpha=1,minimum_signal=2) == 12
    assert _predictive_delta(example(0,now=12)) == 0
    assert _trend_prediction(example(0,now=12),99,alpha=1,minimum_signal=0)==20


def test_change_probability_gate_rejects_uncertain_changes():
    current=example(0,now=8,future=10)
    assert _gated_prediction(current,2,0.59,alpha=1,probability_cutoff=0.6,minimum_correction=0)==8
    assert _gated_prediction(current,2,0.60,alpha=1,probability_cutoff=0.6,minimum_correction=0)==10
    assert _gated_prediction(current,0.4,0.95,alpha=1,probability_cutoff=0.6,minimum_correction=0.5)==8
    with pytest.raises(ValueError,match="Invalid probability"):
        _gated_prediction(current,2,1.2,alpha=1,probability_cutoff=0.6,minimum_correction=0)


def test_stable_training_calibration_selects_zero_correction():
    stable=[example(i*5,now=8,future=8,lag30=6) for i in range(150)]
    trend=select_trend_rule(stable)
    gated=select_gated_rule(stable,[2.0]*150,[0.99]*150)
    assert trend["parameter_tuple"][0]==0.0
    assert gated["parameter_tuple"][0]==0.0
    assert trend["selected_calibration_mae"]==0
    assert gated["grid_size"]>25


def test_true_changes_calibration_can_select_positive_correction():
    rows=[example(i*5,now=8,future=10,lag30=6) for i in range(150)]
    trend=select_trend_rule(rows)
    gate=select_gated_rule(rows,[2.0]*150,[0.95]*150)
    assert trend["parameter_tuple"][0]>0
    assert gate["parameter_tuple"][0]>0
    assert trend["selected_calibration_mae"] < trend["baseline_calibration_mae"]
    assert gate["selected_calibration_mae"] < gate["baseline_calibration_mae"]


def test_research_training_remains_inside_train_and_skips_old_test():
    pytest.importorskip("sklearn")
    captures=[T,T+timedelta(days=1),T+timedelta(days=10)]
    train=[
        example(i*5,now=4+(i%9),future=4+((i+1)%9),lag30=4+((i-6)%9))
        for i in range(6*24*12-8)
    ]
    val=[
        example(6*24*60+i*5,now=4+(i%9),future=4+((i+1)%9),lag30=4+((i-6)%9))
        for i in range(145)
    ]
    report=compare_stability_methods(train,val,captures,
        min_core=150,min_calibration=100,min_validation=100)
    assert report["status"]=="research_comparison_only_no_promoted_model"
    assert set(report["historical_validation"])=={
        "persistence","residual_ml","v23_conservative",
        "simple_bounded_trend","classified_stability_gate",
    }
    assert report["old_p5_test_block_never_loaded"] is True
    assert report["safe_to_publish_forecasts"] is False
    assert report["rule_selection"]["trend"]["tuned_only_on_past_train_calibration"]
    assert report["rule_selection"]["change_gate"]["tuned_only_on_past_train_calibration"]
    assert report["historical_validation"]["persistence"]["pairs"] == len(val)


def test_old_test_rows_rejected_from_validation():
    captures=[T,T+timedelta(days=1),T+timedelta(days=10)]
    with pytest.raises(ValueError,match="Validation outside"):
        compare_stability_methods(
            [example(0)], [example(9*24*60)],captures,
            min_core=1,min_calibration=1,min_validation=1
        )


def test_cli_rejects_thin_fixture_history_and_no_model_artifacts(tmp_path):
    dbfile=tmp_path/"fixtures.sqlite"
    with sqlite3.connect(dbfile) as db:
        db.execute("CREATE TABLE ingestion_runs(run_id TEXT,started_at TEXT,status TEXT)")
        db.execute("INSERT INTO ingestion_runs VALUES (?,?,?)",("fixture",T.isoformat(),"success"))
    evidence=tmp_path/"fixture-evidence.json"
    evidence.write_text(json.dumps([
        {"run_id":"fixture","asset":"synthetic-only.tar.gz","status":"success"},
    ]),encoding="utf-8")
    output=tmp_path/"research"
    response=run("sqlite:///"+str(dbfile),evidence,output)
    assert response["status"]=="not_ready"
    assert response["model_exported"] is False
    assert response["forecast_exported"] is False
    assert response["safe_to_publish_forecasts"] is False
    assert [p.name for p in output.iterdir()] == ["V2_3_1_STABILITY_COMPARISON.json"]
    (output/"model.joblib").write_bytes(b"fixture")
    with pytest.raises(ValueError,match="may not contain deployable"):
        run("sqlite:///"+str(dbfile),evidence,output)
