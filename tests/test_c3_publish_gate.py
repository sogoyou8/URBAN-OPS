"""C3 uses synthetic fixtures ONLY inside tests, never in a release."""
from datetime import datetime, timedelta, timezone
import json
import pytest
from scripts import c3_publish_gate as gate

NOW=datetime(2026,10,22,0,0,tzinfo=timezone.utc)

def fixture(tmp_path,monkeypatch):
    base=tmp_path/"bundle"
    (base/"data").mkdir(parents=True)
    doc={"captured_at":(NOW-timedelta(minutes=45)).isoformat(),
         "dataset_type":"archived_p3_observations",
         "forecast":{"status":"unavailable"},
         "metrics":{"stations":1515,"usable":1490}}
    provenance={"forecast":"not_validated","mode":"archive_not_live"}
    manifest={"status":"publication_ready_not_deployed"}
    def save():
        (base/"data/network.json").write_text(json.dumps(doc))
        (base/"provenance.json").write_text(json.dumps(provenance))
        (base/"manifest.json").write_text(json.dumps(manifest))
    save()
    monkeypatch.setattr(gate,"verify",lambda _:{"validated":True,"files":11})
    return base,doc,provenance,save

def test_accepts_fresh_qualified_archived_observatory_without_p5(tmp_path,monkeypatch):
    base,_,_,_=fixture(tmp_path,monkeypatch)
    result=gate.approve_package(base,now=NOW)
    assert result["publishable_archive"] is True
    assert result["forecast_status"]=="unavailable"
    assert result["measured_stations"]==1490
    assert result["age_hours"]==0.75

def test_rejects_stale_data_and_zero_usable_stations(tmp_path,monkeypatch):
    base,doc,_,save=fixture(tmp_path,monkeypatch)
    doc["captured_at"]=(NOW-timedelta(hours=6)).isoformat()
    save()
    with pytest.raises(ValueError,match="too old"):
        gate.approve_package(base,now=NOW)
    doc["captured_at"]=(NOW-timedelta(minutes=20)).isoformat()
    doc["metrics"]["usable"]=0
    save()
    with pytest.raises(ValueError,match="zero-usable"):
        gate.approve_package(base,now=NOW)

def test_rejects_premature_forecasts_and_realtime_claims(tmp_path,monkeypatch):
    base,doc,provenance,save=fixture(tmp_path,monkeypatch)
    doc["forecast"]["status"]="ready"
    save()
    with pytest.raises(ValueError,match="Unvalidated"):
        gate.approve_package(base,now=NOW)
    doc["forecast"]["status"]="unavailable"
    provenance["mode"]="live"
    save()
    with pytest.raises(ValueError,match="archived"):
        gate.approve_package(base,now=NOW)

def test_rejects_future_data_and_untrustworthy_coverage(tmp_path,monkeypatch):
    base,doc,_,save=fixture(tmp_path,monkeypatch)
    doc["captured_at"]=(NOW+timedelta(hours=1)).isoformat()
    save()
    with pytest.raises(ValueError,match="too old/new"):
        gate.approve_package(base,now=NOW)
    doc["captured_at"]=(NOW-timedelta(minutes=5)).isoformat()
    doc["metrics"]["usable"]=2000
    save()
    with pytest.raises(ValueError,match="coverage"):
        gate.approve_package(base,now=NOW)
