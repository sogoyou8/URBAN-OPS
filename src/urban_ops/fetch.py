"""Network extraction with finite timeouts and bounded GET retries."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import INFO_URL, STATUS_URL


def fetch_pair(timeout_seconds=20.0):
    retries = Retry(
        total=3,
        connect=3,
        read=2,
        status=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        backoff_factor=1.0,
        respect_retry_after_header=True,
    )
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retries))
        result = []
        for url in (INFO_URL, STATUS_URL):
            response = session.get(
                url, timeout=timeout_seconds,
                headers={"User-Agent": "UrbanOps/0.3 (portfolio education; responsible public API usage)"},
            )
            response.raise_for_status()
            if len(response.content) > 15_000_000:
                raise ValueError(f"Upstream payload unexpectedly large: {url}")
            result.append(response.content)
        return tuple(result)
