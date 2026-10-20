"""Convert a Cloudflare R2 capture to the existing P3 replayable TAR format.

Input files are exported from a PRIVATE R2 bucket. No network credentials required.
No missing historical capture is synthesized.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path

SOURCES = ("station_information", "station_status")
UTC = timezone.utc


def parse_utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Timestamps must carry a UTC offset")
    return value.astimezone(UTC)


def convert(source: Path, destination: Path) -> Path:
    if source.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("Refusing oversized R2 capture")
    record = json.loads(gzip.decompress(source.read_bytes()))
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported Cloudflare archive schema")
    scheduled = parse_utc(record["scheduled_at"])
    captured = parse_utc(record["collected_at"])
    if abs((captured - scheduled).total_seconds()) > 30 * 60:
        raise ValueError("Unexpected collection time far from scheduled time")
    data = {}
    hashes = {}
    sizes = {}
    for name in SOURCES:
        raw = record["raw_json"][name].encode("utf-8")
        expected = record["sha256_raw"][name]
        actual = hashlib.sha256(raw).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
            raise ValueError(f"SHA-256 mismatch for {name}")
        feed = json.loads(raw)
        stations = feed["data"]["stations"]
        if not isinstance(stations, list) or len(stations) != record["counts"][name] or len(stations) < 1000:
            raise ValueError(f"Unexpected station count for {name}")
        published = datetime.fromtimestamp(feed["lastUpdatedOther"], UTC)
        if published != parse_utc(record["feed_updated_at"][name]):
            raise ValueError(f"Feed publication mismatch for {name}")
        hashes[name] = actual
        sizes[name] = len(stations)
        data[f"{name}.json.gz"] = gzip.compress(raw)

    run_id = "cf-" + scheduled.strftime("%Y%m%dT%H%M%SZ")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
    archive_name = f"capture-{scheduled.strftime('%Y%m%dT%H%M%SZ')}-{checksum}.tar.gz"
    output = destination / archive_name
    manifest = {
        "schema_version": 1,
        "source": "Vélib' Métropole public open data (ODbL); Cloudflare R2 raw archive",
        "run_id": run_id,
        "collected_at": captured.isoformat(timespec="seconds"),
        "scheduled_at": scheduled.isoformat(timespec="seconds"),
        "status_feed_updated_at": record["feed_updated_at"]["station_status"],
        "station_info_feed_updated_at": record["feed_updated_at"]["station_information"],
        "info_stations": sizes["station_information"],
        "status_stations": sizes["station_status"],
        "sha256_raw": hashes,
        "origin_archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "origin_backend": "cloudflare-r2",
    }
    data["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    destination.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Archive already exists (not overwriting): {output}")
    with tarfile.open(output, "w:gz") as bundle:
        for name, payload in sorted(data.items()):
            item = tarfile.TarInfo(name)
            item.size = len(payload)
            item.mtime = int(captured.timestamp())
            bundle.addfile(item, io.BytesIO(payload))
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", nargs="+", type=Path, help="Private R2 snapshot-*.json.gz files")
    p.add_argument("--output-dir", type=Path, default=Path("data/captures"))
    args = p.parse_args()
    for source in args.source:
        print(convert(source, args.output_dir))


if __name__ == "__main__":
    main()