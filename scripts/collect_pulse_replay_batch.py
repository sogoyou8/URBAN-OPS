"""One-command interactive browser batch downloader for authorized Pulse replays.

Usage: python -m scripts.collect_pulse_replay_batch --output data/pulse-batch
Executes no network requests unless --run, --owner-approved and an explicitly
approved interval are provided.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from urban_ops.pulse_batch import HOST, CollectionStopped, acquire, prepare


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan or collect network-wide Pulse replays")
    parser.add_argument("--output", type=Path, required=True, help="Private batch directory")
    parser.add_argument("--hours", type=int, default=168, help="1..168 (default 168)")
    parser.add_argument("--anchor-at", type=int, help="UTC Unix minute, fixed on first run")
    parser.add_argument("--run", action="store_true", help="Run authenticated browser collection")
    parser.add_argument("--owner-approved", action="store_true",
                        help="Confirm that the service owner approved the bulk retrieval")
    parser.add_argument("--interval-seconds", type=float,
                        help="Request cadence approved by the service owner (min 5s)")
    args = parser.parse_args(argv)

    if args.run and (not args.owner_approved or args.interval_seconds is None):
        parser.error("--run requires --owner-approved and --interval-seconds")
    if args.run and args.interval_seconds < 5:
        parser.error("--interval-seconds must be at least 5")
    try:
        batch = prepare(args.output, args.hours, args.anchor_at)
    except (ValueError, CollectionStopped) as exc:
        parser.error(str(exc))

    if not args.run:
        print(json.dumps({
            "status": batch["status"], "requests_planned": batch["hours"],
            "first_at_utc": batch["first_at_utc"],
            "last_at_utc": batch["last_at_utc"],
            "stored_windows": len(batch["windows"]),
            "next_step": "Await owner authorization, then --run --owner-approved --interval-seconds N",
        }, ensure_ascii=False, indent=2))
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        parser.error("Install the optional browser dependency: pip install -e '.[pulse]'")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            try:
                context = browser.new_context(accept_downloads=False)
                page = context.new_page()
                page.goto(HOST + "/", wait_until="domcontentloaded")
                print(
                    "In the opened browser, verify the session normally on Vélib’ Pulse.\n"
                    "No browser cookies or tokens will be written to disk."
                )
                input("Once the site confirms access, press Enter here (Ctrl+C cancels): ")
                probe = context.request.get(HOST + "/api/session", timeout=20000)
                try:
                    status = probe.json()
                except ValueError as exc:
                    raise CollectionStopped("Could not verify session status") from exc
                if not probe.ok or not status.get("verified", False):
                    raise CollectionStopped(
                        "Session is not verified; complete verification in the visible site"
                    )
                print("Verified browser session. Starting sequential authorized retrieval.")

                def request(url: str):
                    response = context.request.get(url, timeout=45000)
                    return (response.status, response.body(),
                            {k.lower(): v for k, v in response.headers.items()})

                batch = acquire(
                    args.output, batch, request, interval_seconds=args.interval_seconds
                )
                print(json.dumps({
                    "status": batch["status"],
                    "downloaded_windows": len(batch["windows"]),
                    "location": str(args.output),
                }, ensure_ascii=False, indent=2))
            finally:
                browser.close()
    except (CollectionStopped, KeyboardInterrupt) as exc:
        print(f"Stopped safely: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
