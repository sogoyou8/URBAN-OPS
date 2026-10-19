"""Replay immutable public snapshots downloaded from daily GitHub releases.

Usage: python scripts/replay_capture.py --db-url sqlite:///./data/replayed.sqlite file1.tar.gz ...
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from urban_ops.config import Config
from urban_ops.pipeline import ingest
from scripts.archive_capture import unpack


def replay(paths, config):
    results = []
    for path in sorted(paths):
        manifest, feeds = unpack(Path(path))
        result = ingest(feeds["station_information"], feeds["station_status"], config,
                        run_id=manifest["run_id"],
                        captured_at=datetime.fromisoformat(manifest["collected_at"]))
        results.append({"asset": str(path), "run_id": manifest["run_id"], "status": result["status"]})
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archives", nargs="+", type=Path)
    p.add_argument("--db-url", default="sqlite:///./data/replayed.sqlite")
    p.add_argument("--bronze-dir", type=Path, default=Path("data/replayed-bronze"))
    a = p.parse_args()
    print(json.dumps(replay(a.archives, Config(database_url=a.db_url, bronze_dir=a.bronze_dir)), sort_keys=True))


if __name__ == "__main__":
    main()