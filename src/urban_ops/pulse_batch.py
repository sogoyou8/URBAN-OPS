"""Bounded and resumable *authorized* collection of Vélib' Pulse network replays.

Transport is injected so tests never contact the external service. The CLI
opens a normal interactive browser and allows a human to pass Turnstile.
No cookies, credentials or browser profile are exported to disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .pulse_replay import ReplayValidationError, decode_window

HOST = "https://velib.stanislas.cloud"
PLAN_FILE = "pulse_batch_manifest.json"
MAX_HOURS = 168
MAX_JSON_BYTES = 16 * 1024 * 1024


class CollectionStopped(RuntimeError):
    """Stop immediately, retaining only complete, validated files."""


def utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def make_plan(anchor_at: int, hours: int) -> list[int]:
    """Chronological order: retrieve oldest rolling-retention windows first."""
    if type(anchor_at) is not int or anchor_at < 1 or anchor_at % 60:
        raise ValueError("anchor_at must be a positive Unix minute")
    if type(hours) is not int or not 1 <= hours <= MAX_HOURS:
        raise ValueError("hours must be in [1, 168]")
    return [anchor_at - 3600 * offset for offset in range(hours - 1, -1, -1)]


def _atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def prepare(output_dir: Path, hours: int, anchor_at: int | None = None,
            now: Callable[[], float] = time.time) -> dict:
    """Persist an immutable plan; a restart resumes its original anchor."""
    manifest_file = output_dir / PLAN_FILE
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("schema") != "urban-ops-pulse-batch-v1":
            raise CollectionStopped("Unsupported batch manifest schema")
        if hours != manifest["hours"]:
            raise CollectionStopped("Hour count differs from saved plan")
        if anchor_at is not None and anchor_at != manifest["anchor_at"]:
            raise CollectionStopped("Anchor differs from saved plan")
        make_plan(manifest["anchor_at"], manifest["hours"])
        return manifest

    selected = (int(now()) // 60 * 60) if anchor_at is None else anchor_at
    endpoints = make_plan(selected, hours)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "urban-ops-pulse-batch-v1",
        "origin": HOST, "source": "velib-pulse-unofficial",
        "training_qualified": False,
        "minutes": 60, "hours": hours, "anchor_at": selected,
        "first_at_utc": utc(endpoints[0]), "last_at_utc": utc(endpoints[-1]),
        "status": "planned", "windows": {},
    }
    _atomic_json(manifest_file, manifest)
    return manifest


def file_path(directory: Path, at: int) -> Path:
    return directory / f"replay-at-{at}.json"


def _validate(raw: bytes, at: int, name: str) -> dict:
    if len(raw) > MAX_JSON_BYTES:
        raise ReplayValidationError(f"{name}: replay is too large")
    detail, _ = decode_window(raw, name)
    if detail["minutes"] != 60:
        raise ReplayValidationError(f"{name}: response is not a 60-minute replay")
    root = json.loads(raw)
    # The service may have a small upstream delay, but cannot return future data.
    if not at - 3600 <= root["from"] <= root["to"] <= at:
        raise ReplayValidationError(f"{name}: window does not match the requested at")
    return detail


def _record(manifest: dict, at: int, detail: dict) -> dict:
    manifest["windows"][str(at)] = {
        "filename": f"replay-at-{at}.json",
        "sha256": detail["source_sha256"],
        "from_utc": detail["from_utc"], "to_utc": detail["to_utc"],
        "baseline_stations": detail["baseline_stations"],
        "frames": detail["frames"], "change_events": detail["change_events"],
    }
    manifest["status"] = "partial"
    return manifest


def acquire(output_dir: Path, manifest: dict, requester: Callable[[str], tuple[int, bytes, dict]],
            interval_seconds: float, sleeper: Callable[[float], None] = time.sleep,
            now: Callable[[], float] = time.time) -> dict:
    """Acquire in series. Never retry on 403/429/400; stop and preserve progress.

    The caller provides an already authorized request function. No Turnstile
    challenge is solved or bypassed by this module.
    """
    if interval_seconds < 5:
        raise ValueError("Interval must be >=5 seconds, and owner-approved")
    plan = make_plan(manifest["anchor_at"], manifest["hours"])
    if manifest["origin"] != HOST or manifest["minutes"] != 60:
        raise CollectionStopped("Unexpected batch destination or window size")
    manifest_file = output_dir / PLAN_FILE
    requested = 0
    for at in plan:
        target = file_path(output_dir, at)
        name = target.name
        if target.exists():
            try:
                info = _validate(target.read_bytes(), at, name)
            except (OSError, ReplayValidationError) as exc:
                raise CollectionStopped(f"Invalid saved file {name}: {exc}") from exc
            entry = manifest["windows"].get(str(at))
            if entry and entry["sha256"] != info["source_sha256"]:
                raise CollectionStopped(f"Source checksum mismatch: {name}")
            _record(manifest, at, info)
            _atomic_json(manifest_file, manifest)
            continue

        # Check retention before requesting anything; never overwrite gaps.
        if at < int(now()) - 7 * 24 * 3600:
            raise CollectionStopped(
                f"Rolling seven-day retention expired for {utc(at)}. "
                "Keep the collected files and start a fresh plan later."
            )
        if requested:
            sleeper(interval_seconds)
        url = f"{HOST}/api/replay?minutes=60&at={at}"
        try:
            status, raw, headers = requester(url)
        except Exception as exc:
            raise CollectionStopped(f"Network error at {utc(at)}: {type(exc).__name__}") from exc
        requested += 1
        if status in (401, 403):
            raise CollectionStopped(
                f"HTTP {status}: browser session or access not permitted; stopped"
            )
        if status == 429:
            after = headers.get("retry-after", "unspecified")
            raise CollectionStopped(f"HTTP 429: stopped; Retry-After={after}")
        if status != 200:
            raise CollectionStopped(f"HTTP {status}: stopped without retry")
        try:
            info = _validate(raw, at, name)
        except (ReplayValidationError, UnicodeError, ValueError) as exc:
            raise CollectionStopped(f"Invalid API replay for {utc(at)}: {exc}") from exc
        tmp = target.with_suffix(".json.tmp")
        try:
            with tmp.open("xb") as out:
                out.write(raw)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        _record(manifest, at, info)
        _atomic_json(manifest_file, manifest)

    manifest["status"] = "collected_not_p5_qualified"
    _atomic_json(manifest_file, manifest)
    return manifest
