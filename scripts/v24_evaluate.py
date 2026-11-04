"""V2.4 future holdout scorer — never trains or selects a model.

Operates only after the frozen future UTC window is complete. Requires a
research model SHA256 from a PRE-window freeze, validated P3 replays and
actual qualified +30m labels on both weekday and weekend dates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

from scripts.p5_exploratory import verified_replay
from urban_ops.p5 import Reservoir, sql_observations, successful_captures
from urban_ops.v2_research import FEATURE_NAMES_V2, stream_v2_examples
from urban_ops.v24_protocol import (
    PROTOCOL, PROTOCOL_FINGERPRINT, actual_labels_gate,
    decision, dt, future_capture_gate,
)
from urban_ops.v23_candidates import score, validation_segments


def _load_frozen(model_path: Path, manifest_path: Path):
    from joblib import load
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    if metadata["protocol_fingerprint"] != PROTOCOL_FINGERPRINT:
        raise ValueError("Frozen manifest protocol digest changed")
    if metadata["protocol"] != PROTOCOL:
        raise ValueError("Frozen parameters differ from registered experiment")
    if metadata["status"] != "frozen_research_only":
        raise ValueError("Unexpected frozen model status")
    frozen_at = datetime.fromisoformat(metadata["frozen_at_utc"])
    if frozen_at >= dt("future_holdout_start_utc"):
        raise ValueError("Candidate frozen after future outcome window started")
    if metadata["train_cutoff_exclusive_utc"] != dt("training_end_exclusive_utc").isoformat():
        raise ValueError("Frozen training cutoff does not match registration")
    if metadata["last_training_capture_utc"] >= dt("training_end_exclusive_utc").isoformat():
        raise ValueError("Training capture overlaps frozen boundary")
    if metadata["challenger_historical_selection_passed"] is not False:
        raise ValueError("Unexpected promotion eligibility in pre-registration")
    if metadata["research_model_filename"] != model_path.name:
        raise ValueError("Incorrect frozen model file")
    if sha256(model_path.read_bytes()).hexdigest() != metadata["research_model_sha256"]:
        raise ValueError("Frozen research model SHA-256 does not match manifest")
    # The file comes from an authorized Github Action in this same repo.
    # joblib is not suitable for untrusted third-party files.
    packed = load(model_path)
    if packed.get("protocol_fingerprint") != PROTOCOL_FINGERPRINT:
        raise ValueError("Frozen model has inconsistent protocol fingerprint")
    if packed.get("train_cutoff_exclusive_utc") != dt("training_end_exclusive_utc").isoformat():
        raise ValueError("Model training cutoff mismatch")
    if packed.get("feature_names") != list(FEATURE_NAMES_V2):
        raise ValueError("Changed V2.2 feature definitions")
    if packed.get("feature_indices") != metadata["feature_indices"]:
        raise ValueError("Feature projection mismatch")
    if packed.get("frozen_at_utc") != metadata["frozen_at_utc"]:
        raise ValueError("Model and manifest freezing times differ")
    return packed, metadata


def evaluate(db_url: str, replay_evidence: Path, frozen_model: Path,
             frozen_manifest: Path, out: Path, *,
             now: datetime | None = None, minimum_replays: int = 900) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).exists() for name in (
        "model.joblib", "station_forecasts_30m.csv", "v2_forecasts.csv",
    )):
        raise ValueError("Cannot reuse directory with deployable artifacts")

    result = {
        "phase": "Urban Ops V2.4 — frozen model against independent future observations",
        "status": "not_ready_future_holdout",
        "protocol": PROTOCOL,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "as_of_utc": now.isoformat(),
        "historical_selection_gate_passed": False,
        "no_model_tuning_or_fitting_on_holdout": True,
        "research_only": True,
        "forecast_exported": False,
        "model_exported": False,
        "safe_to_publish_forecasts": False,
    }
    if now < dt("earliest_evaluation_utc"):
        result["reason"] = "Future evaluation window has not fully closed"
    else:
        replayed = verified_replay(replay_evidence)
        if replayed < minimum_replays:
            result["status"] = "insufficient_verified_future_archives"
            result["verified_future_replays"] = replayed
        else:
            successful = successful_captures(db_url)
            gate = future_capture_gate(successful, now)
            result["future_capture_quality"] = gate
            result["verified_future_replays"] = replayed
            if not gate["ready"]:
                result["status"] = "insufficient_future_capture_coverage"
            else:
                sample = Reservoir(PROTOCOL["evaluation_sample_cap"], PROTOCOL["random_seed"])
                days = Counter()
                stations: set[int] = set()
                start = dt("future_holdout_start_utc")
                end = dt("future_holdout_end_exclusive_utc")
                for _feat, ex in stream_v2_examples(sql_observations(db_url)):
                    if ex is None:
                        continue
                    if not (start <= ex.feature_at < end
                            and start < ex.target_at < end):
                        continue
                    if not (0 <= ex.values[0] <= ex.values[2]
                            and 0 <= ex.target_bikes <= ex.values[2]):
                        raise ValueError("Invalid qualified future bike count")
                    days[ex.feature_at.date().isoformat()] += 1
                    stations.add(ex.station_id)
                    sample.add(ex)
                labels = actual_labels_gate(days, stations)
                result["future_real_label_quality"] = labels
                result["holdout_sample_size"] = len(sample.items)
                if not labels["ready"] or len(sample.items) < 1000:
                    result["status"] = "insufficient_future_qualified_labels"
                else:
                    packed, manifest = _load_frozen(frozen_model, frozen_manifest)
                    observations = sample.items
                    projected = [
                        [ex.values[i] for i in packed["feature_indices"]]
                        for ex in observations
                    ]
                    deltas = packed["model"].predict(projected)
                    baseline = [float(ex.values[0]) for ex in observations]
                    challenger = [
                        max(0.0, min(float(ex.values[2]), float(ex.values[0]) + float(delta)))
                        for ex, delta in zip(observations, deltas)
                    ]
                    result["results"] = {
                        "persistence": score(observations, baseline),
                        "frozen_residual_challenger": score(observations, challenger),
                    }
                    result["decision"] = decision(
                        result["results"]["persistence"]["mae"],
                        result["results"]["frozen_residual_challenger"]["mae"],
                    )
                    result["post_outcome_segments_DESCRIPTIVE_ONLY"] = validation_segments(
                        observations,
                        {"persistence": baseline, "frozen_residual_challenger": challenger},
                    )
                    day_samples = defaultdict(list)
                    for ex, bp, cp in zip(observations, baseline, challenger):
                        day_samples[ex.feature_at.date().isoformat()].append(
                            (ex, bp, cp)
                        )
                    result["by_utc_date_DESCRIPTIVE_ONLY"] = {
                        date: {
                            "pairs_sampled": len(rows),
                            "persistence": score([e for e, _, _ in rows],
                                                 [bp for _, bp, _ in rows]),
                            "challenger": score([e for e, _, _ in rows],
                                                [cp for _, _, cp in rows]),
                        }
                        for date, rows in sorted(day_samples.items())
                    }
                    result["frozen_research_model_sha256"] = manifest["research_model_sha256"]
                    result["model_frozen_at_utc"] = manifest["frozen_at_utc"]
                    result["status"] = "future_evaluated_research_only"
                    result["safe_to_publish_forecasts"] = False

    output = out / "V24_FUTURE_HOLDOUT_REPORT.json"
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description="Independent future V2.4 assessment; no deploy")
    p.add_argument("--db-url", required=True)
    p.add_argument("--replay-evidence", type=Path, required=True)
    p.add_argument("--frozen-model", type=Path, required=True)
    p.add_argument("--frozen-manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("data/v24-evaluation"))
    a = p.parse_args()
    report = evaluate(a.db_url, a.replay_evidence, a.frozen_model,
                      a.frozen_manifest, a.output)
    print(json.dumps({
        "status": report["status"],
        "results": report.get("results"),
        "safe_to_publish_forecasts": report["safe_to_publish_forecasts"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
