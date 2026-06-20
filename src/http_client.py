"""
Shared HTTP helpers.

Design decisions (Betriebskonzept):
- One reusable `httpx.Client` with a timeout, so we don't leak sockets and every
  request has a bounded wait.
- A single `tenacity` retry policy applied to GET helpers: exponential backoff on
  *transient* failures only (network errors, HTTP 429, HTTP 5xx). Client errors
  like 404 are NOT retried — they won't fix themselves.
- httpx bundles `certifi`, so TLS verification works out of the box (Python's
  stdlib urllib failed cert verification on this machine; httpx/requests don't).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Single shared client. Reused across all calls in a run.
_client = httpx.Client(
    timeout=HTTP_TIMEOUT_SECONDS,
    headers={"User-Agent": "seminar-weather-polymarket-ingest/1.0 (research, read-only)"},
    follow_redirects=True,
)


def _is_transient(exc: BaseException) -> bool:
    """Retry network errors and 429/5xx; do not retry 4xx client errors."""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code < 600
    return False


@retry(
    retry=retry_if_exception(_is_transient),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET `url` and return parsed JSON, retrying transient failures.

    Raises the underlying httpx exception if all retries are exhausted, so the
    caller can decide how to degrade (e.g. skip one source without crashing the
    other).
    """
    resp = _client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def close() -> None:
    """Close the shared client. Safe to call at process exit."""
    _client.close()
