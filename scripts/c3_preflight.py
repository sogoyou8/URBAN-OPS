"""C3 publication preflight: verify static P6.9 bundle; NEVER deploy.

This is a technical handoff report, not user consent or a hosting action.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.package_p6_public import verify


def c3_summary(bundle: Path, *, checked_at: datetime | None = None) -> dict:
    checked_at = checked_at or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise ValueError("checked_at must be timezone aware")
    evidence = verify(bundle)
    dataset = json.loads((bundle / "data/network.json").read_text(encoding="utf-8"))
    provenance = json.loads((bundle / "provenance.json").read_text(encoding="utf-8"))
    if dataset.get("forecast", {}).get("status") != "unavailable":
        raise ValueError("Refuse public package with forecasts until P5 independently validated")
    if provenance.get("mode") != "archive_not_live":
        raise ValueError("Site must remain visibly based on archived observations")
    return {
        "phase": "C3 — hosting handoff; no deployment",
        "status": "technical_preflight_passed_human_checks_pending",
        "technical_checks": {
            "immutable_whitelisted_files_and_sha256": evidence["validated"],
            "archived_observation_only": True,
            "p5_predictions_disabled": True,
            "no_extra_secrets_or_fixtures": True,
            "source_provenance_present": True,
        },
        "captured_at_utc": evidence["captured_at_utc"],
        "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
        "bundle_size_bytes": evidence["size_bytes"],
        "deployment_performed": False,
        "public_url": None,
        "requires_explicit_manual_approval": True,
        "remaining_checks": [
            "Inspect generated bundle on Windows desktop and mobile",
            "Approve public hosting destination and website visibility",
            "Configure GitHub Pages and its domain only after approval",
            "Inspect public URL, external tiles/fonts fallback and live cache freshness",
            "Choose publication cadence and revalidate current verified P3 archive per rebuild",
        ],
        "publishing_rules": {
            "do_not_publish_stale_or_failed_archives": True,
            "fallback_to_last_verified_public_bundle": True,
            "no_prediction_if_not_validated": True,
            "no_synthetic_data": True,
        },
    }


def main() -> None:
    p=argparse.ArgumentParser(description="C3 technical preflight without enabling public hosting")
    p.add_argument("--bundle",type=Path,default=Path("dist/p6-public"))
    p.add_argument("--output",type=Path,default=Path("data/c3-preflight.json"))
    args=p.parse_args()
    result=c3_summary(args.bundle)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
                           encoding="utf-8")
    print(json.dumps({"status":result["status"],"deployment_performed":False,
                      "captured_at_utc":result["captured_at_utc"]},sort_keys=True))


if __name__=="__main__":
    main()
