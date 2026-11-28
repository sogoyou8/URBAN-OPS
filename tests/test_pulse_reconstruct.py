"""Synthetic fixtures only; not real Vélib observations."""
import csv
import json
import pytest
from urban_ops.pulse_reconstruct import reconstruct_replays
from urban_ops.pulse_replay import ReplayValidationError

BASE = 1790000100

def response(start, bikes=3, changes=None):
    frames = changes if changes is not None else []
    return {"v": 1, "minutes": 15, "from": start,
            "to": frames[-1]["observedAt"] if frames else start,
            "baseline": {"observedAt": start, "sourceUpdatedAt": start,
                         "stations": [{"c": 9002, "m": bikes, "e": 1,
                                       "d": 8, "o": 1, "r": start - 20},
                                      {"c": 9003, "m": 2, "e": 0,
                                       "d": 10, "o": 1, "r": start - 20}]},
            "frames": frames}

def frame(at, earlier, new_bikes):
    return {"v": 1, "observedAt": at,
            "previousSourceUpdatedAt": earlier, "sourceUpdatedAt": at,
            "changes": [{"c": 9002, "m": new_bikes, "e": 1,
                         "d": 8, "o": 1, "dm": 1, "de": 0, "dd": 0}]}

def save(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path

def test_sparse_changes_yield_full_station_snapshots(tmp_path):
    a = save(tmp_path / "a.json", response(BASE, changes=[
        frame(BASE + 300, BASE, 4)]))
    b = save(tmp_path / "b.json", response(BASE + 300, bikes=4, changes=[
        frame(BASE + 600, BASE + 300, 5)]))
    audit = reconstruct_replays([b, a], tmp_path / "out")
    assert audit["network_samples_exported"] == 3
    assert audit["station_rows_exported"] == 6
    assert audit["overlapping_frames_skipped"] == 1
    with (tmp_path / "out" / "pulse_network_5m.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert [int(r["num_bikes_available"]) for r in rows if r["station_code"] == "9002"] == [4, 5, 6]
    assert [int(r["num_bikes_available"]) for r in rows if r["station_code"] == "9003"] == [2, 2, 2]

def test_gap_is_measured_not_imputed(tmp_path):
    a = save(tmp_path / "a.json", response(BASE))
    b = save(tmp_path / "b.json", response(BASE + 1200))
    report = reconstruct_replays([a, b], tmp_path / "out")
    assert report["network_samples_exported"] == 2
    assert len(report["gaps_over_threshold"]) == 1
    assert report["nominal_5m_coverage"] == 0.4

def test_conflicting_same_timestamp_rejected(tmp_path):
    a = save(tmp_path / "a.json", response(BASE, changes=[frame(BASE + 300, BASE, 4)]))
    b = save(tmp_path / "b.json", response(BASE + 300, bikes=12))
    with pytest.raises(ReplayValidationError, match="conflicting"):
        reconstruct_replays([a, b], tmp_path / "out")
    assert not (tmp_path / "out" / "pulse_network_5m.csv").exists()


def test_removed_station_not_forward_filled(tmp_path):
    """Pulse sends (m,e,d,o)=(0,0,0,0) as a station removal tombstone."""
    a = response(BASE)
    a["to"] = BASE + 300
    a["frames"] = [{
        "v": 1, "observedAt": BASE + 300,
        "previousSourceUpdatedAt": BASE, "sourceUpdatedAt": BASE + 300,
        "changes": [{
            "c": 9003, "m": 0, "e": 0, "d": 0, "o": 0,
            "dm": 0, "de": 0, "dd": 0,
        }],
    }]
    b = response(BASE + 300, bikes=3, changes=[frame(BASE + 600, BASE + 300, 4)])
    b["baseline"]["stations"] = [s for s in b["baseline"]["stations"] if s["c"] != 9003]
    first = save(tmp_path / "a.json", a)
    second = save(tmp_path / "b.json", b)
    result = reconstruct_replays([first, second], tmp_path / "out")
    assert result["station_removal_events"] == 1
    assert result["network_samples_exported"] == 3
    assert result["station_rows_exported"] == 4  # 2 stations, then 1, then 1
    with (tmp_path / "out" / "pulse_network_5m.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert [r["station_code"] for r in rows].count("9003") == 1
