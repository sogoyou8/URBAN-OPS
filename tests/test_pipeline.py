"""Synthetic fixtures, NEVER observations from the real Vélib' network."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from urban_ops.bronze import archive
from urban_ops.config import Config
from urban_ops.normalize import SourceDataError, read_envelope
from urban_ops.pipeline import ingest
from urban_ops.storage import make_engine, query_summary

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURED = datetime(2026, 10, 19, 11, 19, tzinfo=timezone.utc)


def cfg(tmp_path):
    return Config(database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
                  bronze_dir=tmp_path / "bronze")


def sources():
    return ((FIXTURES / "station_information.json").read_bytes(),
            (FIXTURES / "station_status.json").read_bytes())


def test_bronze_silver_gold_quality(tmp_path):
    c = cfg(tmp_path)
    result = ingest(*sources(), c, captured_at=CAPTURED, run_id="testing-001")
    assert result == {**result, "status": "success"}
    assert result["stations"] == 3
    assert result["status_samples"] == 3
    assert result["quality_issues"] == 2  # 1 capacity mismatch and 1 stale report
    assert result["usable_samples"] == 1
    engine = make_engine(c.database_url)
    counts = query_summary(engine)
    assert counts == dict(runs_succeeded=1, runs_failed=0, stations=3,
                          status_samples=3, usable_samples=1, quality_issues=2,
                          quarantined=0, gold_rows=3)
    with engine.connect() as con:
        row = con.execute(text("SELECT * FROM gold_station_daily WHERE station_id=101")).mappings().one()
        assert row["total_samples"] == 1
        assert row["usable_samples"] == 1
        assert row["empty_samples"] == 1
        assert row["full_samples"] == 0
        assert row["avg_available_bikes"] == 0
        assert row["avg_available_docks"] == 10
        assert row["day_utc"] == "2026-10-19"
        codes = {r[0] for r in con.execute(text("SELECT issue_code FROM data_quality_issues"))}
        assert codes == {"over_declared_capacity", "stale_station_report"}
        snapshots = list(con.execute(text("SELECT path,sha256 FROM raw_snapshots")))
        assert len(snapshots) == 2
        import gzip, hashlib
        for p, h in snapshots:
            assert hashlib.sha256(gzip.open(p, "rb").read()).hexdigest() == h
    engine.dispose()


def test_replay_same_run_no_duplicate(tmp_path):
    c = cfg(tmp_path)
    first = ingest(*sources(), c, run_id="testing-002", captured_at=CAPTURED)
    repeated = ingest(*sources(), c, run_id="testing-002", captured_at=CAPTURED)
    assert first["status"] == "success"
    assert repeated["status"] == "already_completed"
    engine = make_engine(c.database_url)
    assert query_summary(engine)["status_samples"] == 3
    engine.dispose()


def test_new_run_refreshes_gold(tmp_path):
    c = cfg(tmp_path)
    info, status = sources()
    ingest(info, status, c, run_id="testing-003", captured_at=CAPTURED)
    parsed = json.loads(status)
    rec = parsed["data"]["stations"][0]
    rec["num_bikes_available"] = rec["numBikesAvailable"] = 1
    rec["num_docks_available"] = rec["numDocksAvailable"] = 9
    rec["num_bikes_available_types"] = [{"mechanical": 1}, {"ebike": 0}]
    ingest(info, json.dumps(parsed).encode(), c, run_id="testing-004",
           captured_at=CAPTURED + timedelta(minutes=5))
    engine = make_engine(c.database_url)
    assert query_summary(engine)["status_samples"] == 6
    with engine.connect() as con:
        gold = con.execute(text("SELECT * FROM gold_station_daily WHERE station_id=101")).mappings().one()
        assert gold["total_samples"] == gold["usable_samples"] == 2
        assert gold["empty_samples"] == 1
        assert gold["avg_available_bikes"] == 0.5
        latest = con.execute(text("SELECT num_bikes_available FROM vw_station_latest WHERE station_id=101")).scalar_one()
        assert latest == 1
    engine.dispose()


def test_quarantine_orphan(tmp_path):
    info, status = sources()
    doc = json.loads(status)
    row = dict(doc["data"]["stations"][0])
    row["station_id"] = 404
    doc["data"]["stations"].append(row)
    c = cfg(tmp_path)
    result = ingest(info, json.dumps(doc).encode(), c, run_id="testing-005", captured_at=CAPTURED)
    assert result["quarantined"] == 1
    assert result["status_samples"] == 3
    engine = make_engine(c.database_url)
    with engine.connect() as con:
        q = con.execute(text("SELECT station_id,reason,raw_json FROM quarantined_records")).first()
        assert q[0] == 404 and q[1] == "missing_station_information"
        assert json.loads(q[2])["station_id"] == 404
    engine.dispose()


def test_failed_ingestion_is_recorded_and_atomic(tmp_path):
    c = cfg(tmp_path)
    info, _ = sources()
    with pytest.raises(SourceDataError, match="invalid JSON"):
        ingest(info, b"not-json", c, run_id="testing-006", captured_at=CAPTURED)
    engine = make_engine(c.database_url)
    counts = query_summary(engine)
    assert counts["runs_failed"] == 1
    assert counts["status_samples"] == 0
    assert counts["gold_rows"] == 0
    engine.dispose()


def test_validation_does_not_relabel_missing_data_as_zero(tmp_path):
    info, status = sources()
    doc = json.loads(status)
    row = doc["data"]["stations"][0]
    del row["num_bikes_available"]
    c = cfg(tmp_path)
    result = ingest(info, json.dumps(doc).encode(), c, run_id="testing-007", captured_at=CAPTURED)
    assert result["usable_samples"] == 0
    engine = make_engine(c.database_url)
    with engine.connect() as con:
        actual = con.execute(text("SELECT num_bikes_available FROM fact_station_status WHERE station_id=101")).scalar_one_or_none()
        assert actual is None
        codes = [r[0] for r in con.execute(text("SELECT issue_code FROM data_quality_issues"))]
        assert "invalid_counts" in codes
        gold = con.execute(text("SELECT avg_available_bikes FROM gold_station_daily WHERE station_id=101")).scalar_one_or_none()
        assert gold is None
    engine.dispose()


def test_invalid_source_shape():
    with pytest.raises(SourceDataError):
        read_envelope(b'{"lastUpdatedOther": 1, "data": {"stations": []}}', "info")


def test_future_reporting_not_usable(tmp_path):
    info, status = sources()
    doc = json.loads(status)
    doc["data"]["stations"][0]["last_reported"] = doc["lastUpdatedOther"] + 1000
    c = cfg(tmp_path)
    result = ingest(info, json.dumps(doc).encode(), c, run_id="testing-008", captured_at=CAPTURED)
    assert result["usable_samples"] == 0
    engine = make_engine(c.database_url)
    with engine.connect() as con:
        codes = [r[0] for r in con.execute(text("SELECT issue_code FROM data_quality_issues"))]
        assert "station_report_future_of_feed" in codes
    engine.dispose()


def test_bronze_can_be_reopened_for_replay(tmp_path):
    from urban_ops.cli import main
    import gzip
    c = cfg(tmp_path)
    info, status = sources()
    ingest(info, status, c, run_id="testing-009", captured_at=CAPTURED)
    files = list((tmp_path / "bronze").rglob("*.gz"))
    assert len(files) == 2
    info_file = next(x for x in files if x.name.startswith("station_information"))
    status_file = next(x for x in files if x.name.startswith("station_status"))
    assert gzip.open(info_file, "rb").read() == info
    assert gzip.open(status_file, "rb").read() == status
    main(["--database-url", c.database_url, "--bronze-dir", str(c.bronze_dir),
          "collect", "--run-id", "testing-010", "--information-file", str(info_file),
          "--status-file", str(status_file)])
    engine = make_engine(c.database_url)
    assert query_summary(engine)["status_samples"] == 6
    engine.dispose()


def test_batch_1519_synthetic_station_rows(tmp_path):
    """Scale smoke test; generated fixture is NOT Vélib' public dataset."""
    meta, status = json.loads(sources()[0]), json.loads(sources()[1])
    station0 = meta["data"]["stations"][0]
    status0 = status["data"]["stations"][0]
    meta["data"]["stations"] = [dict(station0, station_id=10000000000 + i, stationCode=f"X{i:04d}")
                                   for i in range(1519)]
    status["data"]["stations"] = [dict(status0, station_id=10000000000 + i, stationCode=f"X{i:04d}")
                                   for i in range(1519)]
    c = cfg(tmp_path)
    result = ingest(json.dumps(meta).encode(), json.dumps(status).encode(), c,
                    run_id="testing-large", captured_at=CAPTURED)
    assert result["stations"] == 1519
    assert result["status_samples"] == 1519
    assert result["quality_issues"] == 0
    engine = make_engine(c.database_url)
    summary = query_summary(engine)
    assert summary["status_samples"] == 1519
    assert summary["gold_rows"] == 1519
    engine.dispose()
