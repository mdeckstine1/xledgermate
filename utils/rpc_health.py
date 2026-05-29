"""Detect unhealthy XRPL JSON-RPC endpoints (e.g. amendment-blocked cluster nodes)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

AMENDMENT_BLOCKED_HINT = (
    "The XRPL node at your RPC URL is amendment-blocked (outdated rippled). "
    "Reads and submits can fail at random on public clusters. "
    "In config.yaml set xrpl_mainnet_rpc_url to https://s1.ripple.com:51234 "
    "(or https://s2.ripple.com:51234), save, and retry."
)

_RETRYABLE_RPC_ERRORS = frozenset({"amendmentBlocked", "noNetwork", "notSynced"})


def is_retryable_rpc_error(exc: BaseException) -> bool:
    error = getattr(exc, "error", None)
    if error in _RETRYABLE_RPC_ERRORS:
        return True
    message = str(exc)
    return "amendmentBlocked" in message or "Amendment blocked" in message


def amendment_blocked_message(exc: BaseException) -> str:
    return f"{exc} — {AMENDMENT_BLOCKED_HINT}"


def rpc_reports_amendment_blocked(rpc_url: str, *, timeout: float = 12.0) -> Optional[bool]:
    """Return True/False from server_info, or None if the check could not run."""
    url = (rpc_url or "").strip()
    if not url:
        return None
    body = json.dumps({"method": "server_info", "params": [{}]}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        logger.debug("RPC health check failed for %s: %s", url, exc)
        return None

    info = payload.get("result", {}).get("info", {})
    if not isinstance(info, dict):
        return None
    return bool(info.get("amendment_blocked", False))


async def request_with_retry(client: Any, request: Any, *, attempts: int = 4) -> Any:
    """Retry JSON-RPC when a load-balanced node is temporarily unhealthy."""
    last_exc: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            return await client.request(request)
        except Exception as exc:
            last_exc = exc
            if not is_retryable_rpc_error(exc) or attempt >= attempts - 1:
                raise
            logger.warning(
                "XRPL RPC attempt %s/%s failed (%s); retrying…",
                attempt + 1,
                attempts,
                exc,
            )
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("XRPL RPC request failed with no response")
