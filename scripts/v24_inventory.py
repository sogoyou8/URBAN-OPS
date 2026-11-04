"""V2.4 preflight: inspect names/dates of public P3 release archives only.

Never treats filenames as confirmed valid observations. SHA verification and
qualified future labels are separate required gates after archive replay.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import os

from scripts.audit_collector import ASSET, TAG, fetch_inventory
from urban_ops.v24_protocol import (
    PROTOCOL, PROTOCOL_FINGERPRINT, dt, future_capture_gate,
)


def inventory(inventory: list[dict], now: datetime) -> dict:
    start = dt("future_holdout_start_utc")
    end = dt("future_holdout_end_exclusive_utc")
    unique_instants = set()
    tags = set()
    assets_seen = set()
    for release in inventory:
        tag = release.get("tag_name", "")
        if not TAG.fullmatch(tag):
            continue
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            match = ASSET.fullmatch(name)
            if not match:
                continue
            t = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if t.date().isoformat() != tag[11:] or not start <= t < end:
                continue
            unique_instants.add(t)
            tags.add(tag)
            assets_seen.add(name)
    evidence = future_capture_gate(unique_instants, now)
    evidence["assets_matching_range"] = len(assets_seen)
    evidence["selected_release_tags"] = sorted(tags)
    evidence["protocol_fingerprint"] = PROTOCOL_FINGERPRINT
    evidence["source"] = "GitHub Release ASSET NAMES only; not SHA or qualified labels"
    return evidence


def main():
    p = argparse.ArgumentParser(description="V2.4 future inventory / prereg gate")
    p.add_argument("--repo", default="sogoyou8/URBAN-OPS")
    p.add_argument("--output", type=Path, default=Path("data/v24-inventory.json"))
    a = p.parse_args()
    now = datetime.now(timezone.utc)
    # Short-circuit before the fixed date: no need to scan release assets early.
    if now < dt("earliest_evaluation_utc"):
        info = inventory([], now)
    else:
        fetched = fetch_inventory(a.repo, os.getenv("GH_TOKEN", ""), now, 24*20)
        info = inventory(fetched, now)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(info, sort_keys=True, indent=2, ensure_ascii=False)+"\n",
                        encoding="utf-8")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fp:
            fp.write("ready=" + ("true" if info["ready"] else "false") + "\n")
    print(json.dumps({
        "status": "eligible_metadata_only" if info["ready"] else "awaiting_future_data",
        "time_closed": info["checks"]["time_window_ended"],
        "distinct_slots": info["distinct_5m_slots"],
        "ready_for_SHA_replay": info["ready"],
        "safe_to_publish_forecasts": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
