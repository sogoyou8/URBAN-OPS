"""Reconstruct audited 5-minute network states from authorized, offline Pulse replays.

A replay frame updates a global network state. Unchanged stations are copied
from the *known baseline* within each authorized replay window (never inferred
across missing periods). These are reconstructed network states at real frame
timestamps, not fresh individual station reports and not qualified P3 rows.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .pulse_replay import ReplayValidationError, decode_window, _station

FIELDS = (
    "observed_at_utc", "source_updated_at_utc", "five_minute_bucket_utc",
    "station_code", "mechanical_bikes", "electric_bikes", "num_bikes_available",
    "num_docks_available", "operational_flag", "source_file", "source_sha256",
)


def _utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _fingerprint(states: dict[int, tuple[int, int, int, int]]) -> bytes:
    """Stable digest of all station states to detect conflicting overlaps."""
    digest = hashlib.sha256()
    for code, state in sorted(states.items()):
        digest.update(f"{code}:{state[0]}:{state[1]}:{state[2]}:{state[3]};".encode())
    return digest.digest()


def _parse_validated(path: Path):
    raw = path.read_bytes()
    detail, _ = decode_window(raw, path.name)  # Validate every chain before use.
    root = json.loads(raw)
    return detail, root


def reconstruct_replays(paths: list[Path], output_dir: Path, *,
                        max_gap_seconds: int = 600) -> dict:
    """Stage full network samples at actual source instants, one per 5-min UTC bin.

    Never fetches from the network. Reconstructed rows are intentionally separate
    from P3/P5. A later *explicit* source-specific qualification will be required.
    """
    if not paths:
        raise ValueError("At least one authorized replay JSON file is required")
    if max_gap_seconds <= 0:
        raise ValueError("max_gap_seconds must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "pulse_network_5m.csv"
    manifest_path = output_dir / "pulse_network_audit.json"
    if csv_path.exists() or manifest_path.exists():
        raise FileExistsError("Reconstructed export exists; choose an empty output directory")
    csv_tmp = csv_path.with_suffix(".csv.tmp")
    manifest_tmp = manifest_path.with_suffix(".json.tmp")

    # First pass: validate every input and order by the actual, not filename, time.
    inventory = []
    names, digests = set(), set()
    for path in paths:
        if path.name in names:
            raise ReplayValidationError(f"duplicate source filename: {path.name}")
        names.add(path.name)
        detail, _ = _parse_validated(path)
        if detail["source_sha256"] in digests:
            raise ReplayValidationError(f"duplicate content: {path.name}")
        digests.add(detail["source_sha256"])
        inventory.append((detail["from_utc"], detail["to_utc"], path, detail))
    inventory.sort(key=lambda row: (row[0], row[1], row[2].name))

    audit = {
        "schema": "urban-ops-pulse-network-5m-v1",
        "source": "velib-pulse-unofficial",
        "training_qualified": False,
        "semantics": "global network state at a real Pulse baseline or frame timestamp",
        "policy": "last available actual frame within each UTC 5-minute bucket",
        "sparse_interpolation": False,
        "station_reported_timestamp_known_for_frames": False,
        "windows": [item[3] for item in inventory],
        "network_frames_seen": 0, "network_samples_exported": 0,
        "station_rows_exported": 0,
        "overlapping_frames_skipped": 0,
        "gaps_over_threshold": [],
        "maximum_observed_gap_seconds": 0,
        "nominal_5m_coverage": 0.0,
        "first_sample_utc": None, "last_sample_utc": None,
        "distinct_stations_seen": 0,
    }
    unique_codes = set()
    last_at = None
    last_signature = None
    last_bucket = None
    pending = None
    observed_intervals = []

    def flush(writer):
        nonlocal pending
        if pending is None:
            return
        at, source_at, states, fname, sha = pending
        bucket_at = at - at % 300
        for code, (mechanical, electric, docks, operational) in sorted(states.items()):
            writer.writerow({
                "observed_at_utc": _utc(at), "source_updated_at_utc": _utc(source_at),
                "five_minute_bucket_utc": _utc(bucket_at), "station_code": code,
                "mechanical_bikes": mechanical, "electric_bikes": electric,
                "num_bikes_available": mechanical + electric,
                "num_docks_available": docks, "operational_flag": operational,
                "source_file": fname, "source_sha256": sha,
            })
        audit["network_samples_exported"] += 1
        audit["station_rows_exported"] += len(states)
        if audit["first_sample_utc"] is None:
            audit["first_sample_utc"] = _utc(at)
        audit["last_sample_utc"] = _utc(at)
        pending = None

    try:
        with csv_tmp.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()

            for _, _, path, expected in inventory:
                detail, root = _parse_validated(path)
                if detail["source_sha256"] != expected["source_sha256"]:
                    raise ReplayValidationError(f"input file changed while importing: {path}")
                base = root["baseline"]
                state = {}
                for row in base["stations"]:
                    s = _station(row, baseline=True)
                    state[s["station_code"]] = (
                        s["mechanical_bikes"], s["electric_bikes"],
                        s["num_docks_available"], s["operational_flag"],
                    )
                unique_codes.update(state)
                def process(at, source_at):
                    nonlocal last_at, last_signature, last_bucket, pending
                    audit["network_frames_seen"] += 1
                    signature = _fingerprint(state)
                    if last_at is not None and at <= last_at:
                        audit["overlapping_frames_skipped"] += 1
                        if at == last_at and last_signature != signature:
                            raise ReplayValidationError(
                                f"conflicting network states at {_utc(at)}"
                            )
                        return
                    if last_at is not None:
                        gap = at - last_at
                        audit["maximum_observed_gap_seconds"] = max(
                            audit["maximum_observed_gap_seconds"], gap
                        )
                        if gap > max_gap_seconds:
                            audit["gaps_over_threshold"].append({
                                "from_utc": _utc(last_at), "to_utc": _utc(at),
                                "seconds": gap,
                            })
                    last_at, last_signature = at, signature
                    bucket = at // 300
                    if last_bucket is not None and bucket > last_bucket:
                        flush(writer)
                    if last_bucket is not None and bucket < last_bucket:
                        raise ReplayValidationError("unsorted replay timestamps")
                    last_bucket = bucket
                    pending = (at, source_at, state.copy(), path.name,
                               detail["source_sha256"])

                process(base["observedAt"], base["sourceUpdatedAt"])
                for frame in root["frames"]:
                    for row in frame["changes"]:
                        s = _station(row, baseline=False)
                        state[s["station_code"]] = (
                            s["mechanical_bikes"], s["electric_bikes"],
                            s["num_docks_available"], s["operational_flag"],
                        )
                        unique_codes.add(s["station_code"])
                    process(frame["observedAt"], frame["sourceUpdatedAt"])
            flush(writer)
        audit["distinct_stations_seen"] = len(unique_codes)
        first, last = audit["first_sample_utc"], audit["last_sample_utc"]
        if first is not None and last is not None:
            first_sec = int(datetime.fromisoformat(first).timestamp())
            last_sec = int(datetime.fromisoformat(last).timestamp())
            nominal_buckets = 1 + last_sec // 300 - first_sec // 300
            audit["nominal_5m_coverage"] = round(
                audit["network_samples_exported"] / nominal_buckets, 5
            )
        manifest_tmp.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(csv_tmp, csv_path)
        os.replace(manifest_tmp, manifest_path)
    except Exception:
        csv_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        raise
    return audit
