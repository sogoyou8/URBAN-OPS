"""Release-only eligibility tests for the Vercel archival builder."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.build_vercel_public import recent_assets


class StubResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class StubSession:
    def __init__(self, response):
        self.response = response

    def get(self, url, **kwargs):
        assert url.endswith("/releases?per_page=10")
        return StubResponse(self.response)


def sample(now, lag_minutes=0):
    tag = "velib-data-" + now.strftime("%Y-%m-%d")
    assets = []
    for i in range(12):
        at = now - timedelta(minutes=lag_minutes + i * 5)
        name = f"capture-{at.strftime('%Y%m%dT%H%M%SZ')}-{i:08x}.tar.gz"
        assets.append({
            "name": name,
            "size": 100_000,
            "browser_download_url": (
                f"https://github.com/sogoyou8/URBAN-OPS/releases/download/{tag}/{name}"
            ),
        })
    return [{"tag_name": tag, "assets": assets}]


def test_real_recent_release_selection():
    now = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
    selected = recent_assets(StubSession(sample(now)), now)
    assert len(selected) == 12
    assert selected[-1]["date"] == now
    assert selected == sorted(selected, key=lambda item: item["date"])


def test_refuse_stale_release():
    now = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="too old"):
        recent_assets(StubSession(sample(now, lag_minutes=190)), now)


def test_refuse_wrong_asset_url():
    now = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
    source = sample(now)
    source[0]["assets"][0]["browser_download_url"] = "https://example.org/not-trusted"
    with pytest.raises(ValueError, match="Not enough"):
        recent_assets(StubSession(source), now)
