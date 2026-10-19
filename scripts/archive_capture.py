"""Package one real P3 ingestion into a portable, checksum-verified archive.

The GitHub runner is ephemeral; this archive is uploaded to a *daily Release asset*,
never committed to git history. Offline replay preserves original capture timestamps.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path

SOURCES = ("station_information", "station_status")


def pack(result_path: Path, database_path: Path, bronze_dir: Path, output_dir: Path) -> dict:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "success" or result.get("status_samples", 0) < 1:
        raise ValueError("Collection did not succeed; no archive will be published")
    run_id = result["run_id"]
    with sqlite3.connect(database_path) as db:
        record = db.execute(
            "SELECT started_at, status FROM ingestion_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        rows = db.execute(
            "SELECT source_name,path,sha256,bytes_uncompressed FROM raw_snapshots WHERE run_id=?",
            (run_id,),
        ).fetchall()
    if not record or record[1] != "success":
        raise ValueError("Source ingestion run is not successful in durable local DB")
    captured_at = datetime.fromisoformat(record[0]).astimezone(timezone.utc)
    if not (2 <= len(rows) <= 2) or {r[0] for r in rows} != set(SOURCES):
        raise ValueError("Expected exactly the two official Bronze snapshots")
    files = {}
    for source_name, path, expected_sha, byte_count in rows:
        source_path = Path(path).resolve()
        if not source_path.is_relative_to(bronze_dir.resolve()):
            raise ValueError("Bronze snapshot is outside the configured archive directory")
        compressed = source_path.read_bytes()
        uncompressed = gzip.decompress(compressed)
        if len(uncompressed) != byte_count or hashlib.sha256(uncompressed).hexdigest() != expected_sha:
            raise ValueError(f"Bronze integrity failure: {source_name}")
        decoded = json.loads(uncompressed)
        if not isinstance(decoded.get("data", {}).get("stations"), list):
            raise ValueError(f"Invalid station data for {source_name}")
        files[source_name] = {"bytes": compressed, "sha256": expected_sha,
                              "count": len(decoded["data"]["stations"]),
                              "feed_epoch": decoded["lastUpdatedOther"]}
    if files["station_status"]["count"] < 1000:
        raise ValueError("Station count implausibly low for the active network: stop archiving")
    update_epoch = files["station_status"]["feed_epoch"]
    published = datetime.fromtimestamp(update_epoch, timezone.utc)
    # This is an operational check, not an inferred 'station_reported_at'.
    age = (captured_at - published).total_seconds()
    if age > 30 * 60 or age < -5 * 60:
        raise ValueError(f"Feed publication timestamp is implausible: age_seconds={age}")
    manifest = {
        "schema_version": 1,
        "source": "Vélib' Métropole open data (ODbL), https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole",
        "run_id": run_id,
        "collected_at": captured_at.isoformat(timespec="seconds"),
        "status_feed_updated_at": published.isoformat(timespec="seconds"),
        "station_info_feed_updated_at": datetime.fromtimestamp(files["station_information"]["feed_epoch"], timezone.utc).isoformat(timespec="seconds"),
        "info_stations": files["station_information"]["count"],
        "status_stations": files["station_status"]["count"],
        "normalized_stations": result["stations"],
        "status_samples": result["status_samples"],
        "usable_samples": result["usable_samples"],
        "quality_issues": result["quality_issues"],
        "quarantined": result["quarantined"],
        "sha256_raw": {s: files[s]["sha256"] for s in SOURCES},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    tag = captured_at.strftime("velib-data-%Y-%m-%d")
    basename = f"capture-{captured_at.strftime('%Y%m%dT%H%M%SZ')}-{run_id[:8]}.tar.gz"
    destination = output_dir / basename
    if destination.exists():
        raise FileExistsError(destination)
    with tarfile.open(destination, "w:gz") as archive:
        members = {"manifest.json": (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode()}
        members.update({f"{s}.json.gz": files[s]["bytes"] for s in SOURCES})
        for name, value in members.items():
            item = tarfile.TarInfo(name=name)
            item.size = len(value)
            item.mtime = int(captured_at.timestamp())
            archive.addfile(item, io.BytesIO(value))
    return {"asset": str(destination), "asset_name": destination.name,
            "release_tag": tag, "collected_at": manifest["collected_at"],
            "status_samples": result["status_samples"], "quality_issues": result["quality_issues"],
            "size_bytes": destination.stat().st_size}


def unpack(path: Path):
    """Verify archive without extracting arbitrary tar paths or trusting filenames."""
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
        required = {"manifest.json", "station_information.json.gz", "station_status.json.gz"}
        if names != required:
            raise ValueError("Unexpected members in capture archive")
        data = {name: archive.extractfile(name).read() for name in required}
    manifest = json.loads(data["manifest.json"])
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest schema")
    feeds = {}
    for source in SOURCES:
        raw = gzip.decompress(data[f"{source}.json.gz"])
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest["sha256_raw"][source]:
            raise ValueError(f"Data integrity check failed: {source}")
        feeds[source] = raw
    return manifest, feeds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("data/urban_ops.sqlite"))
    parser.add_argument("--bronze-dir", type=Path, default=Path("data/bronze"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/release-assets"))
    args = parser.parse_args()
    print(json.dumps(pack(args.result, args.db, args.bronze_dir, args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()