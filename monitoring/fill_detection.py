"""Infer buy/sell fills from balance changes between engine cycles."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from connectors.xrpl_connector import is_plausible_rlusd_per_xrp

MIN_RLUSD_DELTA = 0.0001
MIN_XRP_DELTA = 0.00001
# Balance-delta rows below this XRP size with RLUSD movement are usually dust/composite.
MIN_COHERENT_FILL_XRP = 0.01

# Reject composite balance deltas whose implied price is far from mid (deposits, multi-event cycles).
DEFAULT_FILL_PRICE_MAX_REL_DEV = 0.25


def is_coherent_fill_price(
    implied_price: Optional[float],
    mid_price: Optional[float],
    *,
    best_bid: Optional[float] = None,
    best_ask: Optional[float] = None,
    max_relative_deviation: float = DEFAULT_FILL_PRICE_MAX_REL_DEV,
) -> bool:
    """
    True when implied fill price is consistent with a single trade near mid.

    Composite balance bumps (deposit + trade, partial sync) produce implied prices
    that are orders of magnitude off mid — reject those for fill economics.
    """
    if not is_plausible_rlusd_per_xrp(implied_price):
        return False
    if not is_plausible_rlusd_per_xrp(mid_price):
        return False
    implied = float(implied_price)
    mid = float(mid_price)
    if mid <= 0:
        return False
    rel = abs(implied / mid - 1.0)
    if rel > max_relative_deviation:
        return False
    if (
        best_bid is not None
        and best_ask is not None
        and best_bid > 0
        and best_ask > 0
    ):
        lo, hi = min(best_bid, best_ask), max(best_bid, best_ask)
        # Keep the BBO sanity check aligned with the mid guard. A narrower band
        # drops the stale/adverse fills that toxicity tracking most needs to see.
        bbo_low = max(0.0, 1.0 - max_relative_deviation)
        bbo_high = 1.0 + max_relative_deviation
        if not (lo * bbo_low <= implied <= hi * bbo_high):
            return False
    return True


def balance_delta_fill_reject_reason(
    fill: Mapping[str, Any],
    mid_price: Optional[float],
    *,
    best_bid: Optional[float] = None,
    best_ask: Optional[float] = None,
    max_relative_deviation: float = DEFAULT_FILL_PRICE_MAX_REL_DEV,
) -> Optional[str]:
    """None if fill is coherent; otherwise a short operator-facing reason."""
    try:
        xrp_amt = float(fill.get("xrp_amount") or 0)
    except (TypeError, ValueError):
        xrp_amt = 0.0
    if 0 < xrp_amt < MIN_COHERENT_FILL_XRP:
        return (
            f"tiny XRP delta ({xrp_amt:.6f}) with RLUSD move — skip fill log"
        )
    try:
        implied = float(fill.get("price_rlusd_per_xrp") or 0)
    except (TypeError, ValueError):
        return "missing implied fill price"
    if is_coherent_fill_price(
        implied,
        mid_price,
        best_bid=best_bid,
        best_ask=best_ask,
        max_relative_deviation=max_relative_deviation,
    ):
        return None
    mid_s = f"{float(mid_price):.6f}" if mid_price else "n/a"
    return (
        f"incoherent balance delta vs mid {mid_s} "
        f"(implied {implied:.6f} RLUSD/XRP) — skip fill log"
    )


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
        if abs(dx) >= MIN_XRP_DELTA:
            xrp_amount = abs(dx)
            eff_price = dr / xrp_amount
        else:
            xrp_amount = dr / price if price > 0 else 0.0
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
        if abs(dx) >= MIN_XRP_DELTA:
            xrp_amount = abs(dx)
            eff_price = rlusd_spent / xrp_amount
        else:
            xrp_amount = rlusd_spent / price if price > 0 else 0.0
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
