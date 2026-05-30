"""Spread capture estimates for inferred fills (balance-delta or ledger)."""

from __future__ import annotations

from typing import Optional


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
