"""Spread capture estimates for inferred fills (balance-delta or ledger)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from monitoring.fill_detection import is_coherent_fill_price


def estimate_spread_capture_xrp(
    *,
    side: str,
    xrp_amount: float,
    fill_price_rlusd_per_xrp: float,
    mid_at_quote_rlusd_per_xrp: Optional[float],
) -> float:
    """
    Approximate spread captured in XRP equivalent.

    SELL: filled above mid → positive edge.
    BUY: filled below mid → positive edge.
    """
    if not mid_at_quote_rlusd_per_xrp or mid_at_quote_rlusd_per_xrp <= 0:
        return 0.0
    if xrp_amount <= 0 or fill_price_rlusd_per_xrp <= 0:
        return 0.0

    mid = float(mid_at_quote_rlusd_per_xrp)
    fill = float(fill_price_rlusd_per_xrp)
    amt = float(xrp_amount)

    if str(side).upper() == "SELL":
        edge_rlusd = (fill - mid) * amt
    else:
        edge_rlusd = (mid - fill) * amt

    return edge_rlusd / mid


def mid_from_fill_notes(row: Mapping[str, Any]) -> Optional[float]:
    notes = str(row.get("notes") or "")
    match = re.search(r"@ mid ([0-9.]+)", notes)
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            return None
    try:
        price = float(row.get("price_rlusd_per_xrp") or 0)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def spread_capture_from_fill_row(
    row: Mapping[str, Any],
    *,
    default_half_spread_bps: float = 5.0,
    price_tolerance_bps: float = 0.5,
) -> float:
    """
    Spread capture for one trades-CSV fill row.

    Uses stored profit when present. Balance-delta rows often record fill@mid
    (profit=0); estimate skim as volume × half-spread (typical MM edge at touch).
    Skips incoherent implied prices vs mid in notes (composite balance deltas).
    """
    del price_tolerance_bps  # reserved for future ledger-priced fills
    mid_ref = mid_from_fill_notes(row)
    try:
        implied = float(row.get("price_rlusd_per_xrp") or 0)
    except (TypeError, ValueError):
        implied = 0.0
    if (
        mid_ref is not None
        and implied > 0
        and not is_coherent_fill_price(implied, mid_ref)
    ):
        return 0.0
    try:
        stored = float(row.get("profit_xrp_equiv") or 0)
    except (TypeError, ValueError):
        stored = 0.0
    if stored != 0:
        return stored

    side = str(row.get("side") or row.get("event_type") or "").upper()
    if side not in ("BUY", "SELL"):
        return 0.0
    try:
        xrp = float(row.get("xrp_amount") or 0)
    except (TypeError, ValueError):
        xrp = 0.0
    if xrp <= 0:
        return 0.0
    return xrp * default_half_spread_bps / 10_000.0
