"""P6.9: package an audited *archived* public cockpit, never deploy it.

The workflow MUST replay the original signed-by-content (SHA-256) P3 archives
before passing its replay evidence here. This packager does not independently
re-download or verify those archives; it binds the build to the replay result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

KNOWN_SOURCE = "Vélib' Métropole open data (ODbL) via URBAN-OPS P3"
KNOWN_SOURCE_URL = "https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole"
VENDOR_JS = "maplibre-gl.js"
VENDOR_CSS = "maplibre-gl.css"
MAX_PUBLIC_BYTES = 12_000_000
CSP = (
    "default-src 'none'; base-uri 'self'; form-action 'none'; object-src 'none'; "
    "script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "connect-src 'self' https://tiles.openfreemap.org https://*.openfreemap.org; "
    "img-src 'self' data: blob: https://tiles.openfreemap.org https://*.openfreemap.org; "
    "font-src 'self' data: https://fonts.gstatic.com https://tiles.openfreemap.org; "
    "worker-src 'self' blob:; child-src blob:"
)
PUBLIC_FILES = (
    "index.html", "src/main.js", "src/core.js", "src/history.js", "src/style.css",
    "data/network.json", "vendor/maplibre-gl.js", "vendor/maplibre-gl.css"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed_utc(s: str) -> datetime:
    v = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if v.tzinfo is None:
        raise ValueError("Naive capture timestamp is not trustworthy")
    return v.astimezone(timezone.utc)


def checked_input(data: dict, replay: list, now: datetime, max_age_hours: float) -> None:
    if (data.get("schema_version") != 1 or
        data.get("dataset_type") != "archived_p3_observations" or
        data.get("source") != KNOWN_SOURCE or data.get("source_url") != KNOWN_SOURCE_URL):
        raise ValueError("Reject non-P3 or fabricated source metadata")
    if data.get("forecast", {}).get("status") != "unavailable":
        raise ValueError("P5 predictions are not approved for this release")
    if not isinstance(replay, list) or not replay:
        raise ValueError("No P3 replay evidence list")
    metrics = data.get("metrics", {})
    stations = data.get("stations")
    if (not isinstance(stations, list) or not 1000 <= len(stations) <= 3000
        or metrics.get("stations") != len(stations)
        or not isinstance(data.get("history"), list)
        or not 1 <= metrics.get("capture_count", 0) <= len(replay)):
        raise ValueError("P3 station or historical evidence is inconsistent")
    captured = parsed_utc(data["captured_at"])
    age = (now - captured).total_seconds() / 3600
    if not -0.10 <= age <= max_age_hours:
        raise ValueError(f"Archive is not fresh enough to prepare public build ({age:.2f}h)")
    if not isinstance(replay, list) or not replay or any(
        not isinstance(item, dict) or item.get("status") != "success" or
        not str(item.get("asset", "")).endswith(".tar.gz") or
        not str(item.get("run_id", ""))
        for item in replay
    ):
        raise ValueError("Cannot attest verified successful P3 replay")
    ids = [item["run_id"] for item in replay]
    if len(ids) != len(set(ids)) or data.get("run_id") not in ids:
        raise ValueError("Latest capture does not match unique replay evidence")
    if re.search(r"(?i)^(test|mock|fixture|synthetic)", str(data["run_id"])):
        raise ValueError("Refusing test fixture as public data")
    raw = json.dumps(data, ensure_ascii=False)
    if any(token in raw for token in ("TEST_BROWSERS_ONLY", "SYNTHETIC BROWSER FIXTURE", "GITHUB_DISPATCH_TOKEN", "ghp_")):
        raise ValueError("Fixture or credential marker found in public payload")
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in {"password", "private_key", "secret", "email", "api_key", "access_token"}:
                    raise ValueError("Sensitive data key in public payload")
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(data)


def rewrite_html(html: str) -> str:
    old_css = 'href="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.css"'
    old_js = 'src="https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.js"'
    if html.count(old_css) != 1 or html.count(old_js) != 1:
        raise ValueError("Unexpected external MapLibre tags; do not build insecure bundle")
    html = html.replace(old_css, 'href="./vendor/maplibre-gl.css"')
    html = html.replace(old_js, 'src="./vendor/maplibre-gl.js"')
    html = html.replace('<meta charset="utf-8"/>',
                        '<meta charset="utf-8"/>\n  <meta http-equiv="Content-Security-Policy" content="' + CSP + '"/>\n  <meta name="referrer" content="strict-origin-when-cross-origin"/>')
    if html.count('http-equiv="Content-Security-Policy"') != 1:
        raise ValueError("Missing Content Security Policy")
    return html


def prepare(source: Path, out: Path, vendor: Path, evidence: Path, *,
            now: datetime | None = None, max_age_hours: float = 24,
            commit_sha: str = "local-preflight", run_id: str = "local-preflight") -> dict:
    now = now or datetime.now(timezone.utc)
    data_path = source / "data/network.json"
    raw = data_path.read_bytes()
    if len(raw) > 3_000_000:
        raise ValueError("Station JSON exceeds public performance budget (3 MB)")
    data = json.loads(raw)
    replay = json.loads(evidence.read_text(encoding="utf-8"))
    checked_input(data, replay, now, max_age_hours)
    if any(not (source / p).is_file() for p in ("index.html", "src/main.js", "src/core.js", "src/history.js", "src/style.css")):
        raise ValueError("Missing app source")
    if any(not (vendor / p).is_file() or (vendor / p).stat().st_size < 100 for p in (VENDOR_JS, VENDOR_CSS)):
        raise ValueError("Missing local vendored MapLibre bundle")
    if out.resolve() == source.resolve() or source.resolve() in out.resolve().parents:
        raise ValueError("Refusing to overwrite source app")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for rel in ("src/main.js", "src/core.js", "src/history.js", "src/style.css", "data/network.json"):
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, path)
    (out / "index.html").write_text(rewrite_html((source / "index.html").read_text(encoding="utf-8")), encoding="utf-8")
    (out / "vendor").mkdir()
    shutil.copy2(vendor / VENDOR_JS, out / "vendor" / VENDOR_JS)
    shutil.copy2(vendor / VENDOR_CSS, out / "vendor" / VENDOR_CSS)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    provenance = {
        "schema_version": 1, "mode": "archive_not_live", "forecast": "not_validated",
        "source": KNOWN_SOURCE, "source_url": KNOWN_SOURCE_URL,
        "captured_at_utc": data["captured_at"], "generated_at_utc": data.get("generated_at"),
        "p3_latest_run_id": data["run_id"],
        "sha256_network_json": sha256(out / "data/network.json"),
        "verified_p3_replay_count": len(replay),
        "verify_method": "scripts.replay_capture / archive_capture.unpack SHA-256, CI gate",
        "commit_sha": commit_sha, "github_actions_run_id": str(run_id),
        "assembled_at_utc": now.isoformat(timespec="seconds"),
        "limitations": "This file attests this CI build's replay results; it is not a cryptographic publisher signature."
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digests = {p: sha256(out / p) for p in (*PUBLIC_FILES, "provenance.json")}
    manifest = {
        "schema_version": 1, "status": "publication_ready_not_deployed",
        "files_sha256": digests,
        "asset_count": len(digests), "bytes_including_data": sum((out / p).stat().st_size for p in digests),
        "captured_at_utc": data["captured_at"],
        "github_actions_run_id": str(run_id),
        "note": "No hosting has been enabled. Source data is an archived observation, NOT real time."
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verify(out)
    return manifest


def verify(out: Path) -> dict:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "publication_ready_not_deployed":
        raise ValueError("Manifest status cannot assert a deployed site")
    expected = set(PUBLIC_FILES) | {"provenance.json", "manifest.json", ".nojekyll"}
    actual = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    if actual != expected:
        raise ValueError(f"Unexpected/missing release files: {actual ^ expected}")
    digests = manifest.get("files_sha256", {})
    if set(digests) != expected - {"manifest.json", ".nojekyll"}:
        raise ValueError("Unexpected files in digest manifest")
    for path, digest in digests.items():
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(out / path) != digest:
            raise ValueError(f"SHA-256 mismatch: {path}")
    if manifest["bytes_including_data"] > MAX_PUBLIC_BYTES:
        raise ValueError("Public bundle exceeds 12 MB budget")
    html = (out / "index.html").read_text(encoding="utf-8")
    if ('http-equiv="Content-Security-Policy"' not in html or
        'script-src \'self\'' not in html or
        'https://cdn.jsdelivr.net/npm/maplibre-gl' in html or
        'src="./vendor/maplibre-gl.js"' not in html):
        raise ValueError("Release must self-host its JS and enforce CSP")
    dataset = json.loads((out / "data/network.json").read_text(encoding="utf-8"))
    provenance = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    if (dataset["forecast"]["status"] != "unavailable" or
        provenance["sha256_network_json"] != sha256(out / "data/network.json") or
        dataset["captured_at"] != provenance["captured_at_utc"] or
        manifest["captured_at_utc"] != provenance["captured_at_utc"]):
        raise ValueError("Dataset and provenance disagree")
    return {"validated": True, "files": len(actual), "size_bytes": manifest["bytes_including_data"],
            "captured_at_utc": manifest["captured_at_utc"]}


def main():
    p = argparse.ArgumentParser(description="Build or verify immutable P6.9 release package, without deploying")
    p.add_argument("--source", type=Path, default=Path("web"))
    p.add_argument("--out", type=Path, default=Path("dist/p6-public"))
    p.add_argument("--vendor", type=Path, default=Path("web/node_modules/maplibre-gl/dist"))
    p.add_argument("--replay-evidence", type=Path, default=Path("data/p6-replay.json"))
    p.add_argument("--max-age-hours", type=float, default=24)
    p.add_argument("--verify-only", action="store_true")
    a = p.parse_args()
    if a.verify_only:
        print(json.dumps(verify(a.out), sort_keys=True))
    else:
        print(json.dumps(prepare(a.source, a.out, a.vendor, a.replay_evidence,
                                 max_age_hours=a.max_age_hours,
                                 commit_sha=os.environ.get("GITHUB_SHA", "local-preflight"),
                                 run_id=os.environ.get("GITHUB_RUN_ID", "local-preflight")), sort_keys=True))


if __name__ == "__main__":
    main()