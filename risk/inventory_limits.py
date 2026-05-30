"""Hard inventory circuit breakers — pause vulnerable side when far from target."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryLimitState:
    xrp_ratio: float
    target_xrp_ratio: float
    deviation: float
    pause_bids: bool
    pause_asks: bool
    summary: str


def assess_inventory_limits(
    *,
    xrp_ratio: float,
    target_xrp_ratio: float,
    max_deviation: float = 0.12,
) -> InventoryLimitState:
    """
    Pause bids when XRP-heavy beyond max_deviation; pause asks when RLUSD-heavy.
    max_deviation is absolute ratio delta (0.12 = 12 percentage points).
    """
    deviation = xrp_ratio - target_xrp_ratio
    cap = max(0.05, float(max_deviation))
    pause_bids = deviation > cap
    pause_asks = deviation < -cap

    if pause_bids and pause_asks:
        summary = "inventory limits: both sides paused (check balances)"
    elif pause_bids:
        summary = (
            f"inventory limit: {xrp_ratio:.0%} XRP vs target {target_xrp_ratio:.0%} "
            f"(+{deviation:.0%}) → pause bids"
        )
    elif pause_asks:
        summary = (
            f"inventory limit: {xrp_ratio:.0%} XRP vs target {target_xrp_ratio:.0%} "
            f"({deviation:.0%}) → pause asks"
        )
    else:
        summary = ""

    return InventoryLimitState(
        xrp_ratio=xrp_ratio,
        target_xrp_ratio=target_xrp_ratio,
        deviation=deviation,
        pause_bids=pause_bids,
        pause_asks=pause_asks,
        summary=summary,
    )
