"""Audit real archived Vélib captures: gaps, freshness and 5-minute target coverage.

This is an inventory and reliability monitor, NOT a scheduler. GitHub Actions
scheduled events can be delayed or dropped. Missing past snapshots cannot be
reconstructed from a later live API response.

Use --inventory-json with fixtures/offline data or --repo for authenticated
GitHub Release asset inventory with explicit pagination.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote

ASSET = re.compile(r"^capture-(\d{8}T\d{6}Z)-[a-f0-9]{8}\.tar\.gz$")
TAG = re.compile(r"^velib-data-(\d{4}-\d{2}-\d{2})$")
NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
UTC = timezone.utc


def timestamp(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def github_list(url: str, token: str) -> list:
    result = []
    while url:
        req = Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "urban-ops-collector-audit/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": "Bearer " + token} if token else {}),
        })
        with urlopen(req, timeout=25) as response:
            page = json.load(response)
            if not isinstance(page, list):
                raise ValueError(f"Expected a paginated array from {url}")
            result.extend(page)
            match = NEXT.search(response.headers.get("Link", ""))
            url = match.group(1) if match else ""
    return result


def fetch_inventory(repo: str, token: str, now: datetime, window_hours: int) -> list:
    if not REPO.fullmatch(repo):
        raise ValueError("Invalid GitHub owner/repository")
    base = "https://api.github.com/repos/" + "/".join(quote(v, safe="") for v in repo.split("/"))
    releases = github_list(base + "/releases?per_page=100", token)
    earliest = (now - timedelta(hours=window_hours)).date() - timedelta(days=1)
    result = []
    for release in releases:
        tag = release.get("tag_name", "")
        m = TAG.fullmatch(tag)
        if not m:
            continue
        try:
            day = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < earliest or day > (now + timedelta(days=1)).date():
            continue
        release_id = int(release["id"])
        assets = github_list(f"{base}/releases/{release_id}/assets?per_page=100", token)
        result.append({"tag_name": tag, "assets": assets})
    return result


def audit(inventory: list, now: datetime | None = None, window_hours: int = 24,
          cadence_minutes: int = 5, stale_minutes: int = 60,
          coverage_target: float = 0.80) -> dict:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must have a UTC offset")
    now = now.astimezone(UTC)
    if window_hours < 1 or cadence_minutes < 1 or stale_minutes < 1:
        raise ValueError("Audit horizon and minutes must be positive")
    since = now - timedelta(hours=window_hours)
    captured = set()
    invalid = []
    for release in inventory:
        tag = release.get("tag_name", "")
        m = TAG.fullmatch(tag)
        if not m:
            continue
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            found = ASSET.fullmatch(name)
            if not found:
                invalid.append(name)
                continue
            dt = datetime.strptime(found.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            if dt.date().isoformat() != m.group(1) or dt > now + timedelta(minutes=5):
                invalid.append(name)
                continue
            if dt >= since:
                captured.add(dt)
    instants = sorted(captured)
    count = len(instants)
    latest = instants[-1] if instants else None
    # A single capture gives no evidence of continuity.
    window_start = max(since, instants[0]) if instants else since
    span_minutes = (now - window_start).total_seconds() / 60
    expected = (1 + math.floor(span_minutes / cadence_minutes)) if count else None
    # One point has no observed interval: reporting 100% would be misleading.
    coverage = min(1.0, count / expected) if expected and count >= 2 else None
    gaps = [round((b - a).total_seconds() / 60, 2)
            for a, b in zip(instants, instants[1:])]
    age = round((now - latest).total_seconds() / 60, 2) if latest else None
    if latest is None:
        status = "no_archives"
    elif age > stale_minutes:
        status = "stale"
    elif span_minutes < 3 * 60:
        status = "warming_up"
    elif coverage is not None and coverage < coverage_target:
        status = "degraded"
    else:
        status = "on_track"
    return {
        "status": status,
        "target_cadence_minutes": cadence_minutes,
        "window_hours": window_hours,
        "observation_window_start_utc": window_start.isoformat(),
        "window_is_full": window_start == since,
        "capture_count": count,
        "latest_capture_utc": latest.isoformat() if latest else None,
        "latest_capture_age_minutes": age,
        "expected_slots_estimate": expected,
        "coverage_estimate": round(coverage, 4) if coverage is not None else None,
        "largest_observed_gap_minutes": max(gaps, default=None),
        "gaps_over_10_minutes": sum(g > 10 for g in gaps),
        "invalid_asset_names": invalid[:10],
        "limitation": ("Coverage is indicative, bounded by the first observed snapshot "
                       "and current time; only actual archives count. GitHub scheduling "
                       "is best effort. No missing snapshots are backfilled."),
    }


def render_summary(info: dict) -> str:
    pct = ("non mesurable" if info["coverage_estimate"] is None else
           f"{info['coverage_estimate'] * 100:.1f}%")
    age = ("inconnue" if info["latest_capture_age_minutes"] is None else
           f"{info['latest_capture_age_minutes']} min")
    return (
        "## URBAN OPS P3.5 — audit des captures réelles\n\n"
        f"- Statut : **{info['status']}**\n"
        f"- Archives uniques sur la période : **{info['capture_count']}**\n"
        f"- Fraîcheur de la dernière archive : **{age}**\n"
        f"- Couverture indicative cible 5 min : **{pct}** "
        f"({info['capture_count']} / {info['expected_slots_estimate'] or '?'} créneaux)\n"
        f"- Fenêtre 24 h complète : **{'oui' if info['window_is_full'] else 'non'}**\n"
        f"- Plus grand écart constaté : **{info['largest_observed_gap_minutes'] or 'non mesurable'} min**\n\n"
        "**Ce rapport ne garantit pas la cadence ni ne remplit les captures absentes.**\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--repo", help="owner/repository; uses GH_TOKEN for pagination")
    src.add_argument("--inventory-json", type=Path)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--cadence-minutes", type=int, default=5)
    parser.add_argument("--stale-minutes", type=int, default=60)
    parser.add_argument("--fail-on-stale", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    now = datetime.now(UTC)
    records = (fetch_inventory(args.repo, os.getenv("GH_TOKEN", ""), now, args.window_hours)
               if args.repo else json.loads(args.inventory_json.read_text(encoding="utf-8")))
    report = audit(records, now=now, window_hours=args.window_hours,
                   cadence_minutes=args.cadence_minutes, stale_minutes=args.stale_minutes)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(encoded)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(encoded, encoding="utf-8")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(render_summary(report) + "\n")
    if report["status"] in ("stale", "no_archives"):
        print("::warning::No fresh persistent capture; check scheduled workflow runs.")
        if args.fail_on_stale:
            raise SystemExit(2)
    elif report["status"] == "degraded":
        print("::warning::Archived snapshot coverage is below the 80% pilot target.")


if __name__ == "__main__":
    main()
