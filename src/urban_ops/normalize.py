"""Validate upstream envelopes, preserve nulls, qualify station facts and anomalies."""
from __future__ import annotations

import json
from datetime import datetime, timezone


class SourceDataError(ValueError):
    pass


def iso_utc(epoch: object) -> str:
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)) or epoch < 0:
        raise SourceDataError(f"Invalid timestamp: {epoch!r}")
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError) as exc:
        raise SourceDataError(f"Invalid epoch: {epoch!r}") from exc


def read_envelope(payload: bytes, name: str) -> tuple[dict, list[dict]]:
    try:
        root = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceDataError(f"{name}: invalid JSON") from exc
    if not isinstance(root, dict):
        raise SourceDataError(f"{name}: expected object")
    data = root.get("data")
    stations = data.get("stations") if isinstance(data, dict) else None
    if not isinstance(stations, list) or not stations:
        raise SourceDataError(f"{name}: missing/non-list/empty data.stations")
    if not all(isinstance(x, dict) for x in stations):
        raise SourceDataError(f"{name}: stations must contain objects")
    iso_utc(root.get("lastUpdatedOther"))
    return root, stations


def id_or_none(value):
    # station IDs may exceed 32-bit integers; bool is deliberately rejected.
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def flags_or_none(value):
    return value if value in (0, 1) and not isinstance(value, bool) else None


def bike_types(types):
    if not isinstance(types, list):
        return None, None
    m, e = None, None
    for item in types:
        if isinstance(item, dict):
            if "mechanical" in item:
                m = int_or_none(item["mechanical"])
            if "ebike" in item:
                e = int_or_none(item["ebike"])
    return m, e


def normalize_information(info_rows):
    clean, problems, seen = [], [], set()
    for index, row in enumerate(info_rows):
        sid = id_or_none(row.get("station_id"))
        if sid is None or sid in seen:
            problems.append((sid, "invalid_or_duplicate_information_id", "error", f"source_index={index}"))
            continue
        seen.add(sid)
        lat, lon, capacity = row.get("lat"), row.get("lon"), int_or_none(row.get("capacity"))
        if (not isinstance(lat, (float, int)) or isinstance(lat, bool) or not -90 <= lat <= 90 or
            not isinstance(lon, (float, int)) or isinstance(lon, bool) or not -180 <= lon <= 180 or
            capacity is None or capacity <= 0):
            problems.append((sid, "invalid_station_metadata", "error", f"source_index={index}"))
            continue
        clean.append({
            "station_id": sid,
            "station_code": str(row.get("stationCode") or ""),
            "station_name": str(row.get("name") or ""),
            "lat": float(lat), "lon": float(lon), "capacity": capacity,
        })
    return clean, problems


def normalize_status(status_rows, info_by_id, feed_updated, collected, max_lag_seconds):
    clean, issues, quarantine, seen = [], [], [], set()
    feed_epoch = int(feed_updated)
    for index, row in enumerate(status_rows):
        sid = id_or_none(row.get("station_id"))
        if sid is None or sid in seen or sid not in info_by_id:
            reason = "invalid_or_duplicate_status_id" if sid is None or sid in seen else "missing_station_information"
            issues.append((sid, reason, "error", f"source_index={index}"))
            quarantine.append((sid, reason, json.dumps(row, ensure_ascii=False, sort_keys=True)))
            continue
        seen.add(sid)
        metadata = info_by_id[sid]
        bikes = int_or_none(row.get("num_bikes_available"))
        docks = int_or_none(row.get("num_docks_available"))
        mechanical, ebike = bike_types(row.get("num_bikes_available_types"))
        installed = flags_or_none(row.get("is_installed"))
        renting = flags_or_none(row.get("is_renting"))
        returning = flags_or_none(row.get("is_returning"))
        reported_epoch = row.get("last_reported")
        try:
            reported = iso_utc(reported_epoch)
            lag = feed_epoch - reported_epoch
        except (SourceDataError, TypeError):
            reported, lag = None, None
            issues.append((sid, "invalid_station_timestamp", "error", f"source_index={index}"))
        valid_counts = all(v is not None and v >= 0 for v in (bikes, docks, mechanical, ebike))
        if not valid_counts:
            issues.append((sid, "invalid_counts", "error", f"source_index={index}"))
        if valid_counts and bikes != mechanical + ebike:
            issues.append((sid, "bike_types_disagree", "error", f"reported={bikes},types={mechanical + ebike}"))
        if valid_counts and bikes + docks > metadata["capacity"]:
            issues.append((sid, "over_declared_capacity", "warning", f"sum={bikes + docks},capacity={metadata['capacity']}"))
        if row.get("stationCode") is not None and str(row["stationCode"]) != metadata["station_code"]:
            issues.append((sid, "station_code_mismatch", "warning", "info/status codes differ"))
        if row.get("numBikesAvailable") is not None and row["numBikesAvailable"] != bikes:
            issues.append((sid, "alias_bikes_mismatch", "warning", "numBikesAvailable != num_bikes_available"))
        if row.get("numDocksAvailable") is not None and row["numDocksAvailable"] != docks:
            issues.append((sid, "alias_docks_mismatch", "warning", "numDocksAvailable != num_docks_available"))
        if any(v is None for v in (installed, renting, returning)):
            issues.append((sid, "invalid_operational_flag", "error", "Expected 0/1"))
        if lag is not None and lag > max_lag_seconds:
            issues.append((sid, "stale_station_report", "warning", f"lag_seconds={int(lag)}"))
        if lag is not None and lag < -300:
            issues.append((sid, "station_report_future_of_feed", "warning", f"lag_seconds={int(lag)}"))
        # Operational means the station allows both renting and returning.
        # Usable additionally requires valid counts, metadata and recent observation.
        operational = installed == renting == returning == 1
        usable = (operational and valid_counts and bikes == mechanical + ebike
                  and bikes + docks <= metadata["capacity"]
                  and lag is not None and 0 <= lag <= max_lag_seconds)
        clean.append({
            "station_id": sid,
            "station_reported_at": reported,
            "collected_at": collected,
            "feed_updated_at": iso_utc(feed_updated),
            "num_bikes_available": bikes,
            "num_docks_available": docks,
            "mechanical_bikes": mechanical,
            "electric_bikes": ebike,
            "is_installed": installed,
            "is_renting": renting,
            "is_returning": returning,
            "reported_lag_seconds": int(lag) if lag is not None else None,
            "is_usable": int(bool(usable)),
        })
    # Missing statuses relative to the station catalog are material facts.
    for sid in info_by_id.keys() - seen:
        issues.append((sid, "missing_station_status", "warning", "No valid status for this station"))
    return clean, issues, quarantine
