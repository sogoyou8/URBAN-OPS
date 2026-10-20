"""P5 real release inventory: fails safe on missing historical coverage.

Scans up to the last ten UTC days with API pagination. A 'ready' gate is only
permission to *attempt* training: final forecast quality remains unproven.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from urban_ops.p5 import readiness
from scripts.audit_collector import ASSET, TAG, fetch_inventory


def inventory_report(inventory: list[dict], now: datetime) -> dict:
    from datetime import timedelta
    collected = set()
    tags = set()
    earliest = now - timedelta(days=10)
    for release in inventory:
        tag = release.get("tag_name", "")
        if not TAG.fullmatch(tag):
            continue
        for asset in release.get("assets", []):
            match = ASSET.fullmatch(asset.get("name", ""))
            if not match:
                continue
            stamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if stamp.date().isoformat() != tag[11:] or not earliest <= stamp <= now:
                continue
            collected.add(stamp)
            tags.add(tag)
    gate = readiness(collected)
    return {"status": "ready_for_training" if gate["ready"] else "insufficient_history",
            "readiness": gate, "source": "GitHub Release asset names (not P3 revalidated content)",
            "release_tags": sorted(tags)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="sogoyou8/URBAN-OPS")
    parser.add_argument("--output", type=Path, default=Path("data/p5-inventory.json"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    records = fetch_inventory(args.repo, os.getenv("GH_TOKEN", ""), now, 240)
    report = inventory_report(records, now)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["readiness"]}, sort_keys=True))
    if os.getenv("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as f:
            f.write("ready=" + ("true" if report["readiness"]["ready"] else "false") + "\n")


if __name__ == "__main__":
    main()