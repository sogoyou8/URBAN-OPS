"""Release archive roundtrip on synthetic fixtures; never pretend these are live."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from urban_ops.config import Config
from urban_ops.pipeline import ingest
from urban_ops.storage import make_engine, query_summary
from scripts.archive_capture import pack, unpack
from scripts.replay_capture import replay


ROOT = Path(__file__).parent / "fixtures"


def test_archive_pack_roundtrip_replay(tmp_path, monkeypatch):
    # The fixture has 3 stations, so explicitly lower the network count guard
    # by providing 1000 replicated unique fixture IDs for a real-scale synthetic test.
    info = json.loads((ROOT / "station_information.json").read_text())
    status = json.loads((ROOT / "station_status.json").read_text())
    info_rows = info["data"]["stations"]
    status_rows = status["data"]["stations"]
    info["data"]["stations"] = []
    status["data"]["stations"] = []
    for offset in range(334):
        for item in info_rows:
            row = dict(item)
            row["station_id"] = row["station_id"] + 10000 * offset
            info["data"]["stations"].append(row)
        for item in status_rows:
            row = dict(item)
            row["station_id"] = row["station_id"] + 10000 * offset
            status["data"]["stations"].append(row)
    t = datetime.fromtimestamp(status["lastUpdatedOther"], timezone.utc)
    c = Config(database_url=f"sqlite:///{tmp_path/'original.sqlite'}", bronze_dir=tmp_path / "bronze")
    first = ingest(json.dumps(info).encode(), json.dumps(status).encode(), c,
                   run_id="testing-large-12345", captured_at=t)
    assert first["status_samples"] == 1002
    summary = tmp_path / "run.json"
    summary.write_text(json.dumps(first))
    packed = pack(summary, tmp_path / "original.sqlite", c.bronze_dir, tmp_path / "assets")
    assert packed["release_tag"].startswith("velib-data-")
    m, content = unpack(Path(packed["asset"]))
    assert m["status_samples"] == 1002
    assert len(json.loads(content["station_information"])["data"]["stations"]) == 1002
    restored = Config(database_url=f"sqlite:///{tmp_path/'restored.sqlite'}", bronze_dir=tmp_path / "restored")
    results = replay([packed["asset"]], restored)
    assert results[0]["status"] == "success"
    repeated = replay([packed["asset"]], restored)
    assert repeated[0]["status"] == "already_completed"
    engine = make_engine(restored.database_url)
    assert query_summary(engine)["status_samples"] == 1002
    engine.dispose()


def test_refuses_invalid_collection(tmp_path):
    f = tmp_path / "invalid.json"
    f.write_text('{"status":"failed","status_samples":0}')
    with pytest.raises(ValueError, match="did not succeed"):
        pack(f, tmp_path / "missing.db", tmp_path / "bronze", tmp_path / "archive")


def test_refuses_tampered_archive(tmp_path):
    import gzip, hashlib, io, tarfile
    from scripts.archive_capture import unpack
    p = tmp_path / "bad.tar.gz"
    m = {"schema_version":1,"sha256_raw": {"station_information": "incorrect", "station_status":"incorrect"}}
    with tarfile.open(p,"w:gz") as tar:
        for n, b in [("manifest.json",json.dumps(m).encode()),("station_information.json.gz",gzip.compress(b'{}')),("station_status.json.gz",gzip.compress(b'{}'))]:
            meta=tarfile.TarInfo(n); meta.size=len(b);tar.addfile(meta,io.BytesIO(b))
    with pytest.raises(ValueError, match="integrity"):
        unpack(p)