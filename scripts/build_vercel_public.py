"""Build a Vercel-ready, SHA-verified Urban Ops V1 snapshot from real P3 Releases.

This prepares an archived observation, not live station availability. P5 remains
unavailable. Any missing, corrupt or stale real capture stops the build.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from scripts.c3_publish_gate import approve_package
from scripts.export_p6 import export
from scripts.package_p6_public import prepare
from scripts.replay_capture import replay
from urban_ops.config import Config

REPO = "sogoyou8/URBAN-OPS"
ASSET = re.compile(r"^capture-(\d{8}T\d{6}Z)-[0-9a-f]{8}\.tar\.gz$")
TAG = re.compile(r"^velib-data-\d{4}-\d{2}-\d{2}$")
MAX_SIZE = 2_000_000


def recent_assets(session: requests.Session, now: datetime) -> list[dict]:
    response = session.get(
        f"https://api.github.com/repos/{REPO}/releases?per_page=10",
        timeout=30, headers={"Accept": "application/vnd.github+json"}
    )
    response.raise_for_status()
    releases = response.json()
    if not isinstance(releases, list):
        raise ValueError("Unexpected GitHub Releases response")
    found = []
    for release in releases:
        tag = release.get("tag_name", "")
        if not TAG.fullmatch(tag):
            continue
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            match = ASSET.fullmatch(name)
            if not match:
                continue
            at = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if at.date().isoformat() != tag.removeprefix("velib-data-"):
                continue
            if not now - timedelta(days=3) <= at <= now + timedelta(minutes=5):
                continue
            url = asset.get("browser_download_url", "")
            if not url.startswith(f"https://github.com/{REPO}/releases/download/{tag}/"):
                continue
            size = asset.get("size")
            if not isinstance(size, int) or not 0 < size <= MAX_SIZE:
                continue
            found.append({"name": name, "date": at, "url": url, "size": size})
    found.sort(key=lambda a: (a["date"], a["name"]), reverse=True)
    chosen = found[:48]
    if len(chosen) < 12:
        raise ValueError("Not enough real captures for a public archive")
    age = now - chosen[0]["date"]
    if not timedelta(minutes=-5) <= age <= timedelta(hours=3):
        raise ValueError("Latest P3 capture is too old; not deploying stale data")
    return sorted(chosen, key=lambda a: a["date"])


def fetch_assets(session: requests.Session, records: list[dict], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    output = []
    for record in records:
        path = directory / record["name"]
        with session.get(record["url"], timeout=45, stream=True) as response:
            response.raise_for_status()
            total = 0
            with path.open("wb") as writer:
                for chunk in response.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_SIZE:
                        raise ValueError("Oversize P3 capture asset")
                    writer.write(chunk)
        if path.stat().st_size != record["size"]:
            raise ValueError(f"Asset size mismatch: {record['name']}")
        output.append(path)
    return output


def main() -> None:
    base = Path("data/vercel-build")
    base.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    captures = recent_assets(session, datetime.now(timezone.utc))
    print("Verified public archive candidates:", len(captures), "latest:", captures[-1]["date"], flush=True)
    archive_paths = fetch_assets(session, captures, base / "captures")
    database = base / "history.sqlite"
    database_url = f"sqlite:///{database.resolve()}"
    records = replay(archive_paths, Config(database_url=database_url, bronze_dir=base / "bronze"))
    if len(records) != len(archive_paths) or any(x["status"] != "success" for x in records):
        raise ValueError("Verified P3 replay failed")
    evidence = base / "replay.json"
    evidence.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    data = export(database_url)
    output = Path("web/data/network.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    subprocess.run(["npm", "install", "--prefix", "web", "--no-save", "--ignore-scripts",
                    "--no-audit", "--no-fund", "maplibre-gl@4.7.1"], check=True)
    bundle = Path("dist/p6-public")
    prepare(Path("web"), bundle, Path("web/node_modules/maplibre-gl/dist"),
            evidence, max_age_hours=3, commit_sha="vercel-git-build", run_id="vercel-build")
    result = approve_package(bundle, max_age_hours=3)
    print("Urban Ops V1 verified Vercel bundle:", json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
