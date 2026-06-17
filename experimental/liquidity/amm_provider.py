"""H2/H1 — fetch XRP/RLUSD AMM implied mid (read-only)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

XRP_DROPS = 1_000_000.0


def _parse_amount_xrp(amount_field: Any) -> Optional[float]:
    if amount_field is None:
        return None
    if isinstance(amount_field, str) and amount_field.isdigit():
        return int(amount_field) / XRP_DROPS
    if isinstance(amount_field, dict):
        val = amount_field.get("value")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    try:
        return float(amount_field) / XRP_DROPS
    except (TypeError, ValueError):
        return None


def _parse_amount_rlusd(amount_field: Any) -> Optional[float]:
    if isinstance(amount_field, dict):
        try:
            return float(amount_field.get("value") or 0)
        except (TypeError, ValueError):
            return None
    try:
        return float(amount_field)
    except (TypeError, ValueError):
        return None


def implied_mid_rlusd_per_xrp_from_amm_info(result: Dict[str, Any]) -> Optional[float]:
    """RLUSD per XRP from amm_info `amount` / `amount2` pair."""
    if not result:
        return None
    a0 = result.get("amount")
    a1 = result.get("amount2")
    xrp = _parse_amount_xrp(a0)
    rlusd = _parse_amount_rlusd(a1)
    if xrp is None or rlusd is None or xrp <= 0:
        xrp = _parse_amount_xrp(a1)
        rlusd = _parse_amount_rlusd(a0)
    if xrp is None or rlusd is None or xrp <= 0:
        return None
    return rlusd / xrp


def fetch_amm_implied_mid_sync(
    *,
    rpc_url: str,
    rlusd_issuer: str,
    rlusd_currency: str = "RLUSD",
    timeout_s: float = 15.0,
) -> Optional[float]:
    """Blocking JSON-RPC amm_info — returns None when pool missing or RPC fails."""
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed — AMM monitor disabled")
        return None

    payload = {
        "method": "amm_info",
        "params": [
            {
                "asset": {"currency": "XRP"},
                "asset2": {
                    "currency": rlusd_currency,
                    "issuer": rlusd_issuer,
                },
            }
        ],
    }
    try:
        resp = requests.post(rpc_url, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        logger.debug("amm_info failed: %s", exc)
        return None

    if body.get("error"):
        return None
    result = body.get("result") or {}
    amm = result.get("amm") or result
    return implied_mid_rlusd_per_xrp_from_amm_info(amm if isinstance(amm, dict) else result)
