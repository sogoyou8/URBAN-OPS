"""Fixtures are synthetic; they are NEVER presented as actual Vélib observations."""
from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.convert_r2_snapshot import convert
from scripts.archive_capture import unpack


class CloudflareImportTests(unittest.TestCase):
    def create_fixture(self, directory: Path, mismatch: bool = False) -> Path:
        observed = "2026-10-20T11:05:00Z"
        published = "2026-10-20T11:04:00Z"
        feeds = {}
        hashes = {}
        for name in ("station_information", "station_status"):
            text = json.dumps({"lastUpdatedOther": int(datetime.fromisoformat(published.replace('Z','+00:00')).timestamp()),
                              "data": {"stations": [{"station_id": i} for i in range(1001)]}})
            feeds[name] = text
            hashes[name] = hashlib.sha256(text.encode()).hexdigest()
        if mismatch:
            hashes["station_status"] = "0" * 64
        envelope = {
            "schema_version": 1,
            "scheduled_at": observed,
            "collected_at": observed,
            "raw_json": feeds,
            "sha256_raw": hashes,
            "counts": {name: 1001 for name in feeds},
            "feed_updated_at": {name: published for name in feeds},
        }
        path = directory / "snapshot.json.gz"
        path.write_bytes(gzip.compress(json.dumps(envelope).encode()))
        return path

    def test_convert_reuses_existing_native_archive_reader(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            native = convert(self.create_fixture(folder), folder / "output")
            manifest, feeds = unpack(native)
            self.assertEqual(manifest["origin_backend"], "cloudflare-r2")
            self.assertEqual(manifest["status_stations"], 1001)
            self.assertEqual(len(json.loads(feeds["station_status"])["data"]["stations"]), 1001)
            with self.assertRaises(FileExistsError):
                convert(folder / "snapshot.json.gz", folder / "output")

    def test_tampered_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                convert(self.create_fixture(folder, mismatch=True), folder / "output")

    def test_no_timestamp_fabrication(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            capture = self.create_fixture(folder)
            obj = json.loads(gzip.decompress(capture.read_bytes()))
            obj["collected_at"] = "2026-10-21T11:05:00Z"
            capture.write_bytes(gzip.compress(json.dumps(obj).encode()))
            with self.assertRaisesRegex(ValueError, "Unexpected collection time"):
                convert(capture, folder / "output")


if __name__ == "__main__":
    unittest.main()