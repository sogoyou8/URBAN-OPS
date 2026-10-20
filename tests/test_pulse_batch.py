"""Only synthetic replay responses: no network and no real Vélib observations."""
import json
from pathlib import Path

import pytest

from urban_ops.pulse_batch import (
    CollectionStopped, acquire, file_path, make_plan, prepare,
)


AT = 1790007600  # 60-second aligned


def replay(at: int) -> bytes:
    start = at - 3600
    return json.dumps({
        "v": 1, "minutes": 60, "generatedAt": at,
        "from": start, "to": at,
        "baseline": {
            "observedAt": start, "sourceUpdatedAt": start,
            "stations": [{"c": 9002, "m": 1, "e": 2, "d": 9, "o": 1, "r": start - 20}],
        },
        "frames": [{
            "v": 1, "observedAt": at,
            "previousSourceUpdatedAt": start, "sourceUpdatedAt": at,
            "changes": [{"c": 9002, "m": 2, "e": 2, "d": 8, "o": 1,
                         "dm": 1, "de": 0, "dd": -1}],
        }],
    }).encode()


def test_plan_oldest_first_no_network(tmp_path):
    assert make_plan(AT, 3) == [AT - 7200, AT - 3600, AT]
    manifest = prepare(tmp_path / "data", hours=3, anchor_at=AT)
    assert manifest["status"] == "planned"
    assert len(manifest["windows"]) == 0
    assert list((tmp_path / "data").glob("replay-at-*")) == []
    reread = prepare(tmp_path / "data", hours=3)
    assert reread["anchor_at"] == AT
    with pytest.raises(CollectionStopped, match="Hour count"):
        prepare(tmp_path / "data", hours=4)
    with pytest.raises(ValueError):
        make_plan(AT, 169)


def test_batch_is_sequential_resumable_and_idempotent(tmp_path):
    dest = tmp_path / "data"
    manifest = prepare(dest, hours=2, anchor_at=AT)
    endpoints = make_plan(AT, 2)
    calls = []
    delays = []

    def partial(url):
        calls.append(url)
        if len(calls) == 1:
            return 200, replay(endpoints[0]), {}
        return 403, b"forbidden", {}

    with pytest.raises(CollectionStopped, match="HTTP 403"):
        acquire(dest, manifest, partial, 5, sleeper=delays.append, now=lambda: AT)
    assert len(calls) == 2
    assert len(delays) == 1
    first = file_path(dest, endpoints[0])
    assert first.exists()
    assert not file_path(dest, endpoints[1]).exists()
    manifest2 = prepare(dest, hours=2)
    assert len(manifest2["windows"]) == 1

    def resumed(url):
        assert url.endswith(f"at={endpoints[1]}")
        return 200, replay(endpoints[1]), {}
    result = acquire(dest, manifest2, resumed, 5, sleeper=delays.append, now=lambda: AT)
    assert result["status"] == "collected_not_p5_qualified"
    assert len(result["windows"]) == 2
    assert len(list(dest.glob("replay-at-*.json"))) == 2
    # Once complete it rechecks local files but sends no more requests.
    def never(url):
        raise AssertionError("No remote access permitted on complete batch")
    acquire(dest, prepare(dest, hours=2), never, 5, sleeper=delays.append, now=lambda: AT)


@pytest.mark.parametrize("status", [400, 429, 500])
def test_error_never_retries_and_never_writes_bad_data(tmp_path, status):
    dest = tmp_path / "data"
    manifest = prepare(dest, hours=1, anchor_at=AT)
    calls = []
    def blocked(url):
        calls.append(url)
        return status, b'{"error":{}}', {"retry-after": "120"}
    with pytest.raises(CollectionStopped):
        acquire(dest, manifest, blocked, 5, now=lambda: AT)
    assert len(calls) == 1
    assert not file_path(dest, AT).exists()


def test_bad_json_rejected_and_saved_file_tampering_detected(tmp_path):
    dest = tmp_path / "data"
    manifest = prepare(dest, hours=1, anchor_at=AT)
    with pytest.raises(CollectionStopped, match="Invalid API replay"):
        acquire(dest, manifest, lambda _: (200, b'{"oops":1}', {}), 5, now=lambda: AT)
    assert not file_path(dest, AT).exists()
    acquire(dest, manifest, lambda _: (200, replay(AT), {}), 5, now=lambda: AT)
    file_path(dest, AT).write_bytes(replay(AT) + b" ")
    with pytest.raises(CollectionStopped, match="checksum mismatch"):
        acquire(dest, prepare(dest, hours=1), lambda _: None, 5, now=lambda: AT)


def test_expired_anchor_fails_without_network(tmp_path):
    manifest = prepare(tmp_path, hours=1, anchor_at=AT)
    with pytest.raises(CollectionStopped, match="retention expired"):
        acquire(tmp_path, manifest, lambda _: (_ for _ in ()).throw(AssertionError()),
                5, now=lambda: AT + 8 * 24 * 3600)
