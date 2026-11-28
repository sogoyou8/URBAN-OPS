"""Reconstruct five-minute network samples from authorized replay files, offline.

No HTTP requests and no insertion into the official P3 or P5 SQL tables.
"""
import argparse
import json
from pathlib import Path

from urban_ops.pulse_reconstruct import reconstruct_replays


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit and reconstruct authorized Pulse replay JSON")
    parser.add_argument("files", nargs="+", type=Path, help="Already saved replay JSON responses")
    parser.add_argument("--output", type=Path, required=True, help="Output folder")
    parser.add_argument("--max-gap-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    result = reconstruct_replays(
        args.files, args.output, max_gap_seconds=args.max_gap_seconds
    )
    print(json.dumps({
        "status": "staged_not_p5_qualified",
        "source": "velib-pulse-unofficial",
        "windows": len(result["windows"]),
        "distinct_stations": result["distinct_stations_seen"],
        "network_samples": result["network_samples_exported"],
        "station_rows": result["station_rows_exported"],
        "coverage": result["nominal_5m_coverage"],
        "gaps": len(result["gaps_over_threshold"]),
        "output": str(args.output),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
