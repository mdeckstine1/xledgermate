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


def trading_fee_bps_from_amm(amm: Dict[str, Any]) -> Optional[float]:
    """XRPL TradingFee is millionths of notional (500 → 0.05% → 5 bps)."""
    raw = amm.get("TradingFee")
    if raw is None:
        return None
    try:
        return round(float(raw) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def fetch_amm_info_sync(
    *,
    rpc_url: str,
    rlusd_issuer: str,
    rlusd_currency: str = "RLUSD",
    timeout_s: float = 15.0,
) -> Optional[Dict[str, Any]]:
    """Blocking amm_info — mid + pool trading fee (read-only)."""
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
    if not isinstance(amm, dict):
        return None
    return {
        "mid": implied_mid_rlusd_per_xrp_from_amm_info(amm),
        "trading_fee": amm.get("TradingFee"),
        "trading_fee_bps": trading_fee_bps_from_amm(amm),
    }


def fetch_amm_implied_mid_sync(
    *,
    rpc_url: str,
    rlusd_issuer: str,
    rlusd_currency: str = "RLUSD",
    timeout_s: float = 15.0,
) -> Optional[float]:
    """Blocking JSON-RPC amm_info — returns None when pool missing or RPC fails."""
    info = fetch_amm_info_sync(
        rpc_url=rpc_url,
        rlusd_issuer=rlusd_issuer,
        rlusd_currency=rlusd_currency,
        timeout_s=timeout_s,
    )
    if not info:
        return None
    mid = info.get("mid")
    return float(mid) if mid is not None else None
