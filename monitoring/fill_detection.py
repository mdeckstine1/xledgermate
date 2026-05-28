"""Infer buy/sell fills from balance changes between engine cycles."""

from __future__ import annotations

from typing import Any, Dict, Optional

MIN_RLUSD_DELTA = 0.0001
MIN_XRP_DELTA = 0.00001


def detect_fill_from_balance_delta(
    *,
    prev_xrp: float,
    prev_rlusd: float,
    curr_xrp: float,
    curr_rlusd: float,
    mid_price: Optional[float],
) -> Optional[Dict[str, Any]]:
    """
    Compare balances at cycle start vs end of previous cycle (before this cycle's refresh).

    Returns dict with side BUY|SELL and amounts, or None if no meaningful trade-like change.
    """
    dx = curr_xrp - prev_xrp
    dr = curr_rlusd - prev_rlusd
    if abs(dr) < MIN_RLUSD_DELTA and abs(dx) < MIN_XRP_DELTA:
        return None

    price = float(mid_price) if mid_price and mid_price > 0 else 0.0

    # RLUSD received → sold XRP (ask fill or similar).
    if dr > MIN_RLUSD_DELTA:
        xrp_amount = abs(dx) if abs(dx) >= MIN_XRP_DELTA else (dr / price if price > 0 else 0.0)
        eff_price = price if price > 0 else (dr / xrp_amount if xrp_amount > 0 else 0.0)
        return {
            "side": "SELL",
            "xrp_amount": xrp_amount,
            "rlusd_amount": dr,
            "price_rlusd_per_xrp": eff_price,
        }

    # RLUSD spent → bought XRP (bid fill).
    if dr < -MIN_RLUSD_DELTA:
        rlusd_spent = abs(dr)
        xrp_amount = abs(dx) if abs(dx) >= MIN_XRP_DELTA else (
            rlusd_spent / price if price > 0 else 0.0
        )
        eff_price = price if price > 0 else (
            rlusd_spent / xrp_amount if xrp_amount > 0 else 0.0
        )
        return {
            "side": "BUY",
            "xrp_amount": xrp_amount,
            "rlusd_amount": rlusd_spent,
            "price_rlusd_per_xrp": eff_price,
        }

    return None
