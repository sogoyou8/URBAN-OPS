"""Synthetic replay fixtures only: these are NOT historical Vélib' observations."""
import csv
import hashlib
import json

import pytest

from urban_ops.pulse_replay import ReplayValidationError, decode_window, import_replays


AT = 1_790_000_000


def sample():
    return {
        "v": 1, "minutes": 15, "generatedAt": AT + 120,
        "from": AT, "to": AT + 60,
        "baseline": {
            "observedAt": AT, "sourceUpdatedAt": AT,
            "stations": [
                {"c": 9002, "m": 3, "e": 2, "d": 8, "o": 1, "r": AT - 20},
                {"c": 9003, "m": 0, "e": 1, "d": 10, "o": 0, "r": 0},
            ],
        },
        "frames": [{
            "v": 1, "observedAt": AT + 60,
            "previousSourceUpdatedAt": AT, "sourceUpdatedAt": AT + 60,
            "changes": [
                {"c": 9002, "m": 4, "e": 1, "d": 8, "o": 1,
                 "dm": 1, "de": -1, "dd": 0},
            ],
        }],
    }


def payload(source=None):
    return json.dumps(sample() if source is None else source, sort_keys=True).encode()


def test_sparse_replay_and_provenance(tmp_path):
    raw = payload()
    source = tmp_path / "hour.json"
    source.write_bytes(raw)
    report = import_replays([source], tmp_path / "out")
    assert report["rows"] == 3
    assert report["source"] == "velib-pulse-unofficial"
    assert report["integration"] == "quarantined_from_p3_p5"
    assert report["windows"][0]["frames"] == 1
    assert report["windows"][0]["source_sha256"] == hashlib.sha256(raw).hexdigest()
    with (tmp_path / "out" / "pulse_replay_sparse.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert [row["event_kind"] for row in rows] == ["baseline", "baseline", "change"]
    assert [row["station_code"] for row in rows] == ["9002", "9003", "9002"]
    assert rows[0]["num_bikes_available"] == "5"
    assert rows[1]["station_reported_at_utc"] == ""
    assert rows[2]["num_bikes_available"] == "5"
    assert rows[2]["delta_electric"] == "-1"
    assert rows[2]["station_reported_at_utc"] == ""
    assert all(row["source_sha256"] == hashlib.sha256(raw).hexdigest() for row in rows)
    assert (tmp_path / "out" / "pulse_replay_manifest.json").is_file()


def test_malformed_chain_is_rejected_without_output(tmp_path):
    broken = sample()
    broken["frames"][0]["previousSourceUpdatedAt"] = AT + 1
    file = tmp_path / "broken.json"
    file.write_bytes(payload(broken))
    with pytest.raises(ReplayValidationError, match="broken sequential"):
        import_replays([file], tmp_path / "out")
    assert not (tmp_path / "out" / "pulse_replay_sparse.csv").exists()
    assert not (tmp_path / "out" / "pulse_replay_manifest.json").exists()


@pytest.mark.parametrize("change,match", [
    (lambda doc: doc["baseline"]["stations"].append(doc["baseline"]["stations"][0].copy()),
     "duplicate baseline"),
    (lambda doc: doc["frames"][0]["changes"].append(doc["frames"][0]["changes"][0].copy()),
     "duplicate change"),
    (lambda doc: doc["frames"][0]["changes"][0].update(m=-1), "invalid integer"),
    (lambda doc: doc.update(to=AT + 120), "differs from last frame"),
    (lambda doc: doc.update(minutes=90), "invalid replay minutes"),
    (lambda doc: doc["frames"][0].update(sourceUpdatedAt=AT), "broken sequential"),
])
def test_invalid_windows(change, match):
    doc = sample()
    change(doc)
    with pytest.raises(ReplayValidationError, match=match):
        decode_window(payload(doc), "fixture.json")


def test_duplicate_import_and_no_overwrite(tmp_path):
    source = tmp_path / "a.json"
    source.write_bytes(payload())
    with pytest.raises(ReplayValidationError, match="duplicate replay content"):
        import_replays([source, tmp_path / "copy.json"], tmp_path / "out")
    # Initial failure should never publish a partial file.
    assert not (tmp_path / "out" / "pulse_replay_sparse.csv").exists()


def test_existing_export_not_overwritten(tmp_path):
    source = tmp_path / "a.json"
    source.write_bytes(payload())
    out = tmp_path / "out"
    first = import_replays([source], out)
    assert first["rows"] == 3
    with pytest.raises(FileExistsError):
        import_replays([source], out)


def test_missing_frames_can_be_valid_baseline_only():
    doc = sample()
    doc["frames"] = []
    doc["to"] = AT
    detail, rows = decode_window(payload(doc), "baseline-only.json")
    assert detail["frames"] == 0
    assert len(rows) == 2
