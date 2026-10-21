"""Synthetic fixture tests only; never real P5 scores."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scripts.p5_exploratory import run, verified_replay

T = datetime(2026, 10, 21, 7, tzinfo=timezone.utc)


def fixture(tmp_path, count=60):
    db = tmp_path / "fixture.sqlite"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE ingestion_runs(run_id TEXT,started_at TEXT,status TEXT);
            CREATE TABLE dim_stations(station_id INTEGER,capacity INTEGER,latitude REAL,longitude REAL);
            CREATE TABLE fact_station_status(id INTEGER,run_id TEXT,station_id INTEGER,
                collected_at TEXT,num_bikes_available INTEGER,num_docks_available INTEGER,
                mechanical_bikes INTEGER,electric_bikes INTEGER,reported_lag_seconds INTEGER,
                is_usable INTEGER);
        """)
        c.execute("INSERT INTO dim_stations VALUES (101,20,48.87,2.32)")
        for i in range(count):
            at=(T+timedelta(minutes=5*i)).isoformat()
            c.execute("INSERT INTO ingestion_runs VALUES (?,?,?)",(f"run{i}",at,"success"))
            bikes=5+(i%4)
            c.execute("INSERT INTO fact_station_status VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (i,f"run{i}",101,at,bikes,20-bikes,bikes,0,60,1))
    evidence=tmp_path/"p3-replay.json"
    evidence.write_text(json.dumps([
        {"asset":f"verified-{i}.tar.gz","run_id":f"run{i}","status":"success"}
        for i in range(count)
    ]),encoding="utf-8")
    return "sqlite:///"+str(db),evidence


def test_exploratory_is_real_pair_preflight_not_model_promotion(tmp_path):
    db,evidence=fixture(tmp_path)
    output=tmp_path/"report"
    result=run(db,output,evidence)
    assert result["replay_archives_verified"]==60
    assert result["production_status"]=="NOT_VALIDATED"
    assert result["safe_to_publish_forecasts"] is False
    assert result["prediction_rows"]==0
    assert result["model_exported"] is False
    assert result["status"]=="insufficient_preview_pairs"
    assert result["release_readiness"]["ready"] is False
    assert result["real_label_pairs"]["train"]["eligible"]>0
    assert result["real_label_pairs"]["test"]["eligible"]>0
    assert result["baseline_only"]["test"]["persistence_mae"] is not None
    assert (output/"P5_EXPLORATORY_ONLY.json").exists()
    assert sorted(x.name for x in output.iterdir())==["P5_EXPLORATORY_ONLY.json"]


def test_failed_or_duplicate_replay_cannot_be_claimed_verified(tmp_path):
    evidence=tmp_path/"replay.json"
    evidence.write_text(json.dumps([{"run_id":"x","asset":"one","status":"failed"}]))
    with pytest.raises(ValueError,match="Expected successful"):
        verified_replay(evidence)
    evidence.write_text(json.dumps([
      {"run_id":"a","asset":"one","status":"success"},
      {"run_id":"a","asset":"two","status":"success"},
    ]))
    with pytest.raises(ValueError,match="Duplicate"):
        verified_replay(evidence)


def test_exploratory_refuses_existing_model_artifact(tmp_path):
    db,evidence=fixture(tmp_path)
    out=tmp_path/"model"
    out.mkdir()
    (out/"model.joblib").write_bytes(b"fake fixture")
    with pytest.raises(ValueError,match="Refusing exploratory"):
        run(db,out,evidence)
