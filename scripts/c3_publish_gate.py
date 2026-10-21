"""Final C3 gate for a *previously checked* immutable P6 bundle, not a deployer.

The GitHub Pages workflow calls this after fetching a successful main-branch
P6 Actions artifact. Running the script locally does not publish anything.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.package_p6_public import parsed_utc, verify


def approve_package(bundle: Path, *, now: datetime | None = None,
                    max_age_hours: float = 3.0) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or max_age_hours <= 0:
        raise ValueError("Expected aware current time and positive freshness limit")
    checked = verify(bundle)
    data = json.loads((bundle / "data/network.json").read_text(encoding="utf-8"))
    provenance = json.loads((bundle / "provenance.json").read_text(encoding="utf-8"))
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    captured = parsed_utc(data["captured_at"])
    age_hours = (now.astimezone(timezone.utc)-captured).total_seconds()/3600
    if not -0.1 <= age_hours <= max_age_hours:
        raise ValueError(f"Capture too old/new for public release: {age_hours:.2f} hours")
    if data["forecast"]["status"] != "unavailable" or provenance["forecast"] != "not_validated":
        raise ValueError("Unvalidated +30-minute predictions must not be published")
    if provenance.get("mode") != "archive_not_live":
        raise ValueError("Public source is archived data, not real time")
    if data.get("dataset_type") != "archived_p3_observations":
        raise ValueError("Unknown source dataset")
    metrics = data.get("metrics",{})
    if not isinstance(metrics.get("usable"),int) or metrics["usable"] <= 0:
        raise ValueError("Refuse to replace a public bundle with a zero-usable capture")
    stations = metrics.get("stations")
    if not isinstance(stations,int) or stations<1000 or metrics["usable"]>stations:
        raise ValueError("Inconsistent geographic coverage")
    if manifest.get("status") != "publication_ready_not_deployed":
        raise ValueError("Bundle must pass the original P6 preflight, not claim deployment")
    return {
        "publishable_archive": True,
        "captured_at_utc": captured.isoformat(),
        "age_hours": round(age_hours,3),
        "measured_stations": metrics["usable"],
        "catalog_stations": stations,
        "forecast_status": "unavailable",
        "source_verified": checked["validated"],
        "files": checked["files"],
    }


def main() -> None:
    p=argparse.ArgumentParser(description="Verify an archived-data P6 build immediately before Pages deployment")
    p.add_argument("--bundle",type=Path,required=True)
    p.add_argument("--max-age-hours",type=float,default=3.0)
    args=p.parse_args()
    print(json.dumps(approve_package(args.bundle,max_age_hours=args.max_age_hours),
                     sort_keys=True,ensure_ascii=False))


if __name__ == "__main__":
    main()
