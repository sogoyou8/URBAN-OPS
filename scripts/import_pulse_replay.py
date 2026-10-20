"""Convert previously obtained, authorized Pulse /api/replay responses offline.

This script makes no network requests and does not modify P3/P5 tables.
"""
import argparse
import json
from pathlib import Path

from urban_ops.pulse_replay import import_replays


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline Pulse replay staging for Urban Ops")
    parser.add_argument("files", nargs="+", type=Path, help="Downloaded JSON responses (15/30/60 min)")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args(argv)
    result = import_replays(args.files, args.output)
    print(json.dumps({
        "status": "staged_not_p5_qualified",
        "files": len(result["windows"]),
        "rows": result["rows"],
        "output": str(args.output),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
