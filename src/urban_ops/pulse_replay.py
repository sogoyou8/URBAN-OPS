"""Offline, provenance-preserving import of authorized Vélib' Pulse replay JSON.

Deliberately separate from official GBFS Bronze/Silver/Gold: Pulse does not
expose all three operational flags or a station report timestamp on changes.
Never silently promote these rows into qualified P3/P5 observations.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class ReplayValidationError(ValueError):
    """Malformed or inconsistent replay window; do not publish partial output."""


FIELDS = (
    "event_kind", "observed_at_utc", "source_updated_at_utc", "station_code",
    "mechanical_bikes", "electric_bikes", "num_bikes_available",
    "num_docks_available", "operational_flag", "station_reported_at_utc",
    "delta_mechanical", "delta_electric", "delta_docks",
    "source_file", "source_sha256",
)


def _integer(value, field: str, minimum: int = 0, maximum: int = 10_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReplayValidationError(f"{field}: invalid integer {value!r}")
    return value


def _utc(seconds: int) -> str:
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError) as exc:
        raise ReplayValidationError(f"invalid UTC timestamp: {seconds!r}") from exc


def _station(row, *, baseline: bool) -> dict:
    if not isinstance(row, dict):
        raise ReplayValidationError("station: expected object")
    required = ("c", "m", "e", "d", "o", "r") if baseline else (
        "c", "m", "e", "d", "o", "dm", "de", "dd"
    )
    if any(key not in row for key in required):
        raise ReplayValidationError("station: missing required keys")
    result = {
        "station_code": _integer(row["c"], "c", 1, 999_999),
        "mechanical_bikes": _integer(row["m"], "m"),
        "electric_bikes": _integer(row["e"], "e"),
        "num_docks_available": _integer(row["d"], "d"),
        "operational_flag": _integer(row["o"], "o", 0, 1),
    }
    result["num_bikes_available"] = result["mechanical_bikes"] + result["electric_bikes"]
    if baseline:
        result["station_reported_at_utc"] = (
            _utc(_integer(row["r"], "r", 0, 9_999_999_999)) if row["r"] else ""
        )
        result.update(delta_mechanical="", delta_electric="", delta_docks="")
    else:
        result["station_reported_at_utc"] = ""  # Not in Pulse's diff schema.
        for key, output in (("dm", "delta_mechanical"), ("de", "delta_electric"),
                            ("dd", "delta_docks")):
            result[output] = _integer(row[key], key, -10_000, 10_000)
    return result


def decode_window(raw: bytes, source_file: str) -> tuple[dict, list[dict]]:
    """Validate one Pulse replay, returning manifest metadata and sparse records."""
    try:
        root = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReplayValidationError(f"{source_file}: invalid JSON") from exc
    if not isinstance(root, dict) or root.get("v") != 1:
        raise ReplayValidationError(f"{source_file}: expected replay version 1")
    minutes = root.get("minutes")
    if type(minutes) is not int or minutes not in (15, 30, 60):
        raise ReplayValidationError(f"{source_file}: invalid replay minutes")
    baseline = root.get("baseline")
    frames = root.get("frames")
    if not isinstance(baseline, dict) or not isinstance(frames, list):
        raise ReplayValidationError(f"{source_file}: missing baseline/frames")
    if not isinstance(baseline.get("stations"), list) or not baseline["stations"]:
        raise ReplayValidationError(f"{source_file}: empty baseline")
    from_at = _integer(root.get("from"), "from", 1, 9_999_999_999)
    to_at = _integer(root.get("to"), "to", 1, 9_999_999_999)
    base_at = _integer(baseline.get("observedAt"), "baseline.observedAt", 1, 9_999_999_999)
    source_at = _integer(baseline.get("sourceUpdatedAt"), "baseline.sourceUpdatedAt", 1, 9_999_999_999)
    if from_at != base_at or to_at < from_at or to_at - from_at > minutes * 60:
        raise ReplayValidationError(f"{source_file}: invalid replay boundaries")
    if "generatedAt" in root:
        _integer(root["generatedAt"], "generatedAt", 1, 9_999_999_999)
    digest = hashlib.sha256(raw).hexdigest()
    records = []
    seen = set()
    def add(kind, row, observed, updated):
        station = _station(row, baseline=kind == "baseline")
        code = station["station_code"]
        result = {
            "event_kind": kind,
            "observed_at_utc": _utc(observed),
            "source_updated_at_utc": _utc(updated),
            **station,
            "source_file": source_file,
            "source_sha256": digest,
        }
        records.append(result)
        return code
    for row in baseline["stations"]:
        code = add("baseline", row, base_at, source_at)
        if code in seen:
            raise ReplayValidationError(f"{source_file}: duplicate baseline station {code}")
        seen.add(code)
    previous_observed, previous_source = base_at, source_at
    changed = 0
    for frame in frames:
        if not isinstance(frame, dict) or frame.get("v") != 1:
            raise ReplayValidationError(f"{source_file}: invalid frame")
        at = _integer(frame.get("observedAt"), "frame.observedAt", 1, 9_999_999_999)
        previous = _integer(frame.get("previousSourceUpdatedAt"), "frame.previousSourceUpdatedAt", 1, 9_999_999_999)
        updated = _integer(frame.get("sourceUpdatedAt"), "frame.sourceUpdatedAt", 1, 9_999_999_999)
        changes = frame.get("changes")
        if (not isinstance(changes, list) or at <= previous_observed
            or updated <= previous_source or previous != previous_source
            or at > to_at):
            raise ReplayValidationError(f"{source_file}: broken sequential replay")
        codes = set()
        for row in changes:
            code = add("change", row, at, updated)
            if code in codes:
                raise ReplayValidationError(f"{source_file}: duplicate change station {code}")
            codes.add(code)
            changed += 1
        previous_observed, previous_source = at, updated
    if previous_observed != to_at:
        raise ReplayValidationError(f"{source_file}: 'to' differs from last frame")
    return {
        "source_file": source_file, "source_sha256": digest,
        "from_utc": _utc(from_at), "to_utc": _utc(to_at),
        "minutes": minutes, "baseline_stations": len(seen),
        "change_events": changed, "frames": len(frames),
    }, records


def import_replays(paths: list[Path], output_dir: Path) -> dict:
    """Offline files only. Refuse overwrite, validate all files before publishing."""
    if not paths:
        raise ValueError("At least one replay JSON file is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "pulse_replay_sparse.csv"
    manifest_path = output_dir / "pulse_replay_manifest.json"
    if csv_path.exists() or manifest_path.exists():
        raise FileExistsError("Pulse export exists; use a fresh output directory")
    csv_tmp = csv_path.with_suffix(".csv.tmp")
    manifest_tmp = manifest_path.with_suffix(".json.tmp")
    manifest = {
        "schema": "urban-ops-pulse-replay-sparse-v1",
        "source": "velib-pulse-unofficial",
        "integration": "quarantined_from_p3_p5",
        "record_semantics": "one baseline row per station, then changed stations only",
        "windows": [],
        "rows": 0,
    }
    try:
        with csv_tmp.open("w", newline="", encoding="utf-8") as dest:
            writer = csv.DictWriter(dest, fieldnames=FIELDS)
            writer.writeheader()
            seen_names = set()
            seen_hashes = set()
            for path in paths:
                if path.name in seen_names:
                    raise ReplayValidationError(f"duplicate filename: {path.name}")
                seen_names.add(path.name)
                detail, rows = decode_window(path.read_bytes(), path.name)
                if detail["source_sha256"] in seen_hashes:
                    raise ReplayValidationError(f"duplicate replay content: {path.name}")
                seen_hashes.add(detail["source_sha256"])
                writer.writerows(rows)
                manifest["windows"].append(detail)
                manifest["rows"] += len(rows)
        manifest_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(csv_tmp, csv_path)
        os.replace(manifest_tmp, manifest_path)
    except Exception:
        csv_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        raise
    return manifest
