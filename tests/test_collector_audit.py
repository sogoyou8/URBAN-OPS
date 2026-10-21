"""P3.5 tests never call GitHub or invent production observations."""
from datetime import datetime, timedelta, timezone
from scripts.audit_collector import audit, render_summary

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def asset(moment):
    return {"name": f"capture-{moment.strftime('%Y%m%dT%H%M%SZ')}-abcdef12.tar.gz"}


def inventory(*moments):
    days = {}
    for moment in moments:
        tag = "velib-data-" + moment.strftime("%Y-%m-%d")
        days.setdefault(tag, []).append(asset(moment))
    return [{"tag_name": tag, "assets": files} for tag, files in days.items()]


def test_one_capture_never_means_full_coverage():
    result = audit(inventory(NOW - timedelta(minutes=1)), now=NOW)
    assert result["status"] == "warming_up"
    assert result["capture_count"] == 1
    assert result["window_is_full"] is False
    assert "100.0%" not in render_summary(result)


def test_regular_captures_can_be_on_track_after_three_hours():
    samples = [NOW - timedelta(minutes=n) for n in range(0, 186, 5)]
    result = audit(inventory(*samples), now=NOW)
    assert result["status"] == "on_track"
    assert result["coverage_estimate"] == 1.0
    assert result["capture_count"] == len(samples)
    assert result["largest_observed_gap_minutes"] == 5.0


def test_realistic_three_hour_schedule_gap_is_detected():
    result = audit(inventory(NOW-timedelta(hours=3), NOW-timedelta(minutes=2)), now=NOW)
    assert result["status"] == "degraded"
    assert result["largest_observed_gap_minutes"] == 178
    assert result["coverage_estimate"] < 0.10
    assert result["gaps_over_10_minutes"] == 1


def test_stale_snapshot_causes_unhealthy_status():
    result = audit(inventory(NOW-timedelta(hours=2)), now=NOW)
    assert result["status"] == "stale"
    assert result["latest_capture_age_minutes"] == 120


def test_empty_history_is_not_available():
    result = audit([], now=NOW)
    assert result["status"] == "no_archives"
    assert result["coverage_estimate"] is None


def test_ignore_wrong_tag_or_future_and_deduplicate():
    stamp = NOW-timedelta(minutes=4)
    entries = inventory(stamp, stamp)
    entries[0]["assets"].extend([
        {"name": "capture-20261001T120000Z-abcdef12.tar.gz"},
        {"name": "notes.txt"},
        asset(NOW + timedelta(minutes=8)),
    ])
    result = audit(entries, now=NOW)
    assert result["capture_count"] == 1
    assert len(result["invalid_asset_names"]) == 3


def test_past_24h_window_excludes_previous_day():
    older = NOW - timedelta(hours=26)
    recent = NOW - timedelta(minutes=7)
    result = audit(inventory(older, recent), now=NOW, window_hours=24)
    assert result["capture_count"] == 1
    assert result["observation_window_start_utc"] == recent.isoformat()



def test_same_five_minute_slot_is_counted_once():
    # Three distinct persisted captures in one UTC slot do not yield 100% coverage.
    entries = inventory(
        NOW - timedelta(minutes=30),
        NOW - timedelta(minutes=29),
        NOW - timedelta(minutes=28),
        NOW - timedelta(minutes=5),
        NOW,
    )
    result = audit(entries, now=NOW, window_hours=1)
    assert result["capture_count"] == 5
    assert result["distinct_cadence_slots"] == 3
    assert result["duplicate_cadence_slot_captures"] == 2
    assert result["coverage_estimate"] < 0.60
    assert result["missing_observed_slots"] > 0


def test_high_coverage_but_long_gap_must_be_degraded():
    # 4 hours of samples at 5 min minus three adjacent slots, still >80%,
    # but there is a 20-minute interruption.
    samples = [
        NOW - timedelta(minutes=5*i)
        for i in range(49) if i not in (17, 18, 19)
    ]
    report = audit(inventory(*samples), now=NOW, window_hours=5)
    assert report["coverage_estimate"] > .80
    assert report["largest_observed_gap_minutes"] == 20
    assert report["gaps_over_healthy_limit"] == 1
    assert report["status"] == "degraded"
    assert report["largest_gap_from_utc"] and report["largest_gap_to_utc"]


def test_full_window_is_reported_only_when_first_slot_present():
    samples = [NOW - timedelta(minutes=5*i) for i in range(289)]
    report = audit(inventory(*samples), now=NOW)
    assert report["window_is_full"] is True
    assert report["coverage_full_window"] == 1.0
    assert report["distinct_cadence_slots"] == 289


def test_24h_full_window_coverage_is_not_hidden_by_late_start():
    samples = [NOW - timedelta(minutes=5*i) for i in range(37)]
    report = audit(inventory(*samples), now=NOW)
    assert report["status"] == "on_track"
    assert report["coverage_estimate"] == 1.0
    assert report["coverage_full_window"] < .20
    assert report["window_is_full"] is False
