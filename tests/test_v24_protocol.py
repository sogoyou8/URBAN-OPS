"""Synthetic contract tests ONLY. No real V2.4 result exists before Nov 4."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json

import pytest

from scripts.v24_inventory import inventory
from scripts.v24_evaluate import evaluate, _load_frozen
from scripts.v24_freeze import freeze
from urban_ops.v24_protocol import (
    PROTOCOL, PROTOCOL_FINGERPRINT, actual_labels_gate,
    check_static_protocol, decision, dt, future_capture_gate,
)

UTC = timezone.utc
START = dt("future_holdout_start_utc")
END = dt("future_holdout_end_exclusive_utc")
AFTER = dt("earliest_evaluation_utc")


def test_dates_and_protocol_hash_locked_to_future_week():
    check_static_protocol()
    assert dt("training_end_exclusive_utc") < START
    assert START == datetime(2026, 10, 28, tzinfo=UTC)
    assert END == datetime(2026, 11, 4, tzinfo=UTC)
    assert AFTER >= END + timedelta(minutes=30)
    assert len(PROTOCOL_FINGERPRINT) == 64
    assert not PROTOCOL["historical_challenger_passed_selection_gate"]
    assert not PROTOCOL["promote_model_automatically"]


def test_future_gate_rejects_data_before_window_ends():
    # Synthetic perfect cadence is not proof of real future archives.
    times = [START+timedelta(minutes=5*i) for i in range(2016)]
    result = future_capture_gate(times, START+timedelta(days=3))
    assert result["distinct_5m_slots"] == 2016
    assert result["ready"] is False
    assert result["checks"]["time_window_ended"] is False


def test_future_gate_checks_real_coverage_and_window_edges():
    times = [START+timedelta(minutes=5*i) for i in range(2016)]
    assert future_capture_gate(times, AFTER)["ready"] is True
    assert future_capture_gate(times[500:], AFTER)["ready"] is False
    assert not future_capture_gate(times[:500], AFTER)["ready"]
    assert future_capture_gate(times[0::5], AFTER)["coverage"] < 0.3


def test_label_gate_requires_real_pairs_each_weekday_and_weekend():
    days = [(START+timedelta(days=i)).date().isoformat() for i in range(7)]
    counts = {x:3000 for x in days}
    good = actual_labels_gate(counts, set(range(350)))
    assert good["ready"] is True
    assert good["weekday_dates_with_labels"] == 5
    assert good["weekend_dates_with_labels"] == 2
    assert good["paired_real_observations_total"] == 21000
    absent_saturday = dict(counts)
    absent_saturday[datetime(2026,10,31,tzinfo=UTC).date().isoformat()] = 0
    assert actual_labels_gate(absent_saturday, set(range(350)))["ready"] is False
    assert actual_labels_gate(counts, set(range(100)))["ready"] is False


def test_positive_future_gain_still_cannot_promote_historically_failed_candidate():
    better = decision(1.0,0.7)
    assert better["future_gain_positive"] is True
    assert better["historical_selection_passed"] is False
    assert better["promotion_eligible"] is False
    assert better["new_model_not_authorized_for_public_predictions"] is True
    assert decision(0.0,0.0)["relative_future_mae_improvement"] is None


def test_github_asset_inventory_is_metadata_only():
    record = {
        "tag_name":"velib-data-2026-10-28",
        "assets":[
            {"name":"capture-20261028T000000Z-aaaaaaaa.tar.gz"},
            {"name":"capture-20261028T000000Z-aaaaaaaa.tar.gz"},
            {"name":"capture-20261028T000500Z-bbbbbbbb.tar.gz"},
            {"name":"capture-20261027T235500Z-cccccccc.tar.gz"},
        ],
    }
    summary = inventory([record], AFTER)
    assert summary["assets_matching_range"] == 2
    assert summary["distinct_5m_slots"] == 2
    assert summary["ready"] is False
    assert "ASSET NAMES" in summary["source"]


def test_frozen_model_cannot_be_started_after_future_window_opens(tmp_path):
    with pytest.raises(ValueError,match="not frozen before future"):
        freeze("sqlite:///missing.sqlite",tmp_path/"missing.json",tmp_path/"freeze",
               now=START)


def test_evaluator_before_final_date_does_not_access_unseen_future(tmp_path):
    output=tmp_path/"report"
    result=evaluate(
        "sqlite:///does-not-exist.sqlite", tmp_path/"missing-replay.json",
        tmp_path/"missing-model.joblib", tmp_path/"missing-manifest.json",
        output, now=START+timedelta(days=3),
    )
    assert result["status"]=="not_ready_future_holdout"
    assert result["safe_to_publish_forecasts"] is False
    assert "model_exported" in result
    assert [p.name for p in output.iterdir()]==["V24_FUTURE_HOLDOUT_REPORT.json"]


def test_model_sha_mismatch_rejected_before_untrusted_deserialization(tmp_path):
    path=tmp_path/"v24_frozen_challenger_research_only.joblib"
    path.write_bytes(b"tampered-joblib-fixture")
    m=tmp_path/"V24_FROZEN_MANIFEST.json"
    m.write_text(json.dumps({
        "protocol_fingerprint":PROTOCOL_FINGERPRINT,
        "protocol":PROTOCOL,
        "status":"frozen_research_only",
        "frozen_at_utc":"2026-10-27T11:00:00+00:00",
        "train_cutoff_exclusive_utc":dt("training_end_exclusive_utc").isoformat(),
        "last_training_capture_utc":"2026-10-27T10:35:00+00:00",
        "challenger_historical_selection_passed":False,
        "research_model_filename":path.name,
        "research_model_sha256":"0"*64,
    }), encoding="utf-8")
    with pytest.raises(ValueError,match="SHA-256"):
        _load_frozen(path,m)


def test_output_directory_with_model_cannot_be_reused_even_before_window(tmp_path):
    out=tmp_path/"research"
    out.mkdir()
    (out/"model.joblib").write_bytes(b"fake")
    with pytest.raises(ValueError,match="deployable"):
        evaluate("sqlite:///none",tmp_path/"none",tmp_path/"none",
                 tmp_path/"none",out,now=START)
