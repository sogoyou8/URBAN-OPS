"""C3 approval boundary and archive semantics; synthetic tiny fixtures only."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import scripts.c3_preflight as c3


def test_c3_preflight_is_not_a_deployment(tmp_path, monkeypatch):
    bundle=tmp_path/"site"
    (bundle/"data").mkdir(parents=True)
    (bundle/"data/network.json").write_text(json.dumps({"forecast":{"status":"unavailable"}}))
    (bundle/"provenance.json").write_text(json.dumps({"mode":"archive_not_live"}))
    monkeypatch.setattr(c3, "verify", lambda _: {
        "validated":True,"size_bytes":8300,
        "captured_at_utc":"2026-10-21T09:06:16+00:00"})
    result=c3.c3_summary(bundle,checked_at=datetime(2026,10,21,tzinfo=timezone.utc))
    assert result["status"]=="technical_preflight_passed_human_checks_pending"
    assert result["deployment_performed"] is False
    assert result["public_url"] is None
    assert result["requires_explicit_manual_approval"] is True
    assert result["technical_checks"]["p5_predictions_disabled"] is True


def test_c3_refuses_premature_p5_or_realtime_claim(tmp_path, monkeypatch):
    site=tmp_path/"site";(site/"data").mkdir(parents=True)
    monkeypatch.setattr(c3,"verify",lambda _:{
        "validated":True,"size_bytes":8300,
        "captured_at_utc":"2026-10-21T09:06:16+00:00"})
    (site/"provenance.json").write_text('{"mode":"archive_not_live"}')
    (site/"data/network.json").write_text('{"forecast":{"status":"ready"}}')
    with pytest.raises(ValueError,match="P5 independently validated"):
        c3.c3_summary(site)
    (site/"data/network.json").write_text('{"forecast":{"status":"unavailable"}}')
    (site/"provenance.json").write_text('{"mode":"live"}')
    with pytest.raises(ValueError,match="archived"):
        c3.c3_summary(site)
