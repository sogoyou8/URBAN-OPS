"""Freeze a V2.4 RESEARCH challenger using pre-registered historical dates only.

The fixed, previously unsuccessful V2.3 residual ML is refitted without tuning.
Weights are stored ONLY as a time-stamped GitHub Actions research artifact,
never on Vercel or in the Git repository. The future-window target is NEVER read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from scripts.p5_exploratory import verified_replay
from urban_ops.p5 import Reservoir, readiness, sql_observations, successful_captures
from urban_ops.v23_candidates import MODEL_PARAMETERS
from urban_ops.v2_research import FEATURE_NAMES_V2, stream_v2_examples
from urban_ops.v24_protocol import PROTOCOL, PROTOCOL_FINGERPRINT, dt


def freeze(db_url: str, verified_replay_path: Path, out: Path, *,
           now: datetime | None = None, min_train: int | None = None) -> dict:
    from joblib import dump
    from sklearn.ensemble import HistGradientBoostingRegressor

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now >= dt("future_holdout_start_utc"):
        raise ValueError("Research model was not frozen before future holdout began")

    if out.exists() and any(out.iterdir()):
        raise ValueError("Never overwrite or refit an existing frozen experiment")
    out.mkdir(parents=True, exist_ok=True)

    replayed = verified_replay(verified_replay_path)
    if replayed < 900:
        raise ValueError("Not enough SHA-checked P3 archive replays")

    cutoff = dt("training_end_exclusive_utc")
    history = [t for t in successful_captures(db_url) if t < cutoff]
    quality = readiness(history)
    if not quality["ready"]:
        raise ValueError("Historical pre-cutoff data fail readiness: " + quality["reason"])

    rows = Reservoir(PROTOCOL["historical_train_sample_cap"], PROTOCOL["random_seed"])
    for _features, ex in stream_v2_examples(sql_observations(db_url)):
        # Any observation after cutoff must NEVER yield a train label.
        if ex is not None and ex.feature_at < cutoff and ex.target_at < cutoff:
            rows.add(ex)

    required = min_train if min_train is not None else PROTOCOL["minimum_historical_train_pairs"]
    if len(rows.items) < required:
        raise ValueError("Insufficient qualified real training labels")
    if any(x.feature_at >= cutoff or x.target_at >= cutoff for x in rows.items):
        raise ValueError("Future label leaked into frozen model")
    indices = [
        i for i in range(len(FEATURE_NAMES_V2))
        if any(math.isfinite(x.values[i]) for x in rows.items)
    ]
    if not indices:
        raise ValueError("No observed P3 training variables")
    model = HistGradientBoostingRegressor(**MODEL_PARAMETERS)
    model.fit(
        [[x.values[i] for i in indices] for x in rows.items],
        [float(x.target_bikes - x.values[0]) for x in rows.items],
    )
    frozen = out / "v24_frozen_challenger_research_only.joblib"
    dump({
        "model": model,
        "feature_indices": indices,
        "feature_names": list(FEATURE_NAMES_V2),
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "frozen_at_utc": now.isoformat(),
        "train_cutoff_exclusive_utc": cutoff.isoformat(),
        "type": "research_only_residual_not_eligible_for_promotion",
    }, frozen)
    digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
    manifest = {
        "status": "frozen_research_only",
        "protocol": PROTOCOL,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "frozen_at_utc": now.isoformat(),
        "train_cutoff_exclusive_utc": cutoff.isoformat(),
        "first_training_capture_utc": quality["from_utc"],
        "last_training_capture_utc": quality["through_utc"],
        "historical_quality": quality,
        "verified_archive_replays": replayed,
        "eligible_real_training_pairs": rows.seen,
        "sampled_training_pairs": len(rows.items),
        "feature_indices": indices,
        "feature_names_used": [FEATURE_NAMES_V2[i] for i in indices],
        "excluded_all_missing_features": [
            name for i, name in enumerate(FEATURE_NAMES_V2) if i not in indices
        ],
        "research_model_sha256": digest,
        "research_model_filename": frozen.name,
        "historical_validation_winner": "persistence",
        "challenger_historical_selection_passed": False,
        "v1_deployed": False,
        "safe_to_publish_forecasts": False,
    }
    (out / "V24_FROZEN_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Pre-holdout freeze, research artifact only")
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--replay-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/v24-frozen"))
    args = parser.parse_args()
    evidence = freeze(args.db_url, args.replay_evidence, args.output)
    print(json.dumps({
        "status": evidence["status"],
        "protocol_sha256": evidence["protocol_fingerprint"],
        "historical_pairs": evidence["eligible_real_training_pairs"],
        "research_only": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
