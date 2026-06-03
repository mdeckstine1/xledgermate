"""Hard inventory circuit breakers — pause vulnerable side when far from target."""

from __future__ import annotations

from dataclasses import dataclass

INVENTORY_MODE_MARKET_MAKE = "market_make"
INVENTORY_MODE_REBALANCE = "rebalance"


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
    inventory_mode: str = INVENTORY_MODE_MARKET_MAKE,
    hard_pause_deviation: float = 0.22,
) -> InventoryLimitState:
    """
    Pause the inventory-vulnerable side when |deviation| exceeds max_deviation.

    Rebalance and market-make both use max_deviation for automatic bailout (default
    12 ratio points). hard_pause_deviation is retained for config compatibility only.
    """
    deviation = xrp_ratio - target_xrp_ratio
    mode = (inventory_mode or INVENTORY_MODE_MARKET_MAKE).strip().lower()
    _ = hard_pause_deviation  # legacy config; bailout uses max_deviation in all modes
    cap = max(0.05, float(max_deviation))

    pause_bids = deviation > cap
    pause_asks = deviation < -cap

    if pause_bids and pause_asks:
        summary = "inventory limits: both sides paused (check balances)"
    elif pause_bids:
        tag = "inventory bailout" if mode == INVENTORY_MODE_MARKET_MAKE else "inventory limit"
        summary = (
            f"{tag}: {xrp_ratio:.0%} XRP vs target {target_xrp_ratio:.0%} "
            f"(+{deviation:.0%}) → pause bids; unload via asks"
        )
    elif pause_asks:
        tag = "inventory bailout" if mode == INVENTORY_MODE_MARKET_MAKE else "inventory limit"
        summary = (
            f"{tag}: {xrp_ratio:.0%} XRP vs target {target_xrp_ratio:.0%} "
            f"({deviation:.0%}) → pause asks; acquire XRP via bids"
        )
    elif mode == INVENTORY_MODE_MARKET_MAKE and abs(deviation) >= 0.05:
        summary = (
            f"MM skew: {xrp_ratio:.0%} XRP vs target {target_xrp_ratio:.0%} "
            f"({deviation:+.0%}) → size skew until {cap:.0%} bailout"
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


def portfolio_xrp_equiv(xrp_balance: float, rlusd_balance: float, mid_price: float) -> float:
    if mid_price <= 0:
        return max(0.0, xrp_balance)
    return xrp_balance + rlusd_balance / mid_price


def max_bid_xrp_without_overshoot(
    *,
    xrp_balance: float,
    rlusd_balance: float,
    mid_price: float,
    target_xrp_ratio: float,
    overshoot_slack: float,
) -> float:
    """Max bid size (XRP) so a full fill does not exceed target + slack."""
    total = portfolio_xrp_equiv(xrp_balance, rlusd_balance, mid_price)
    if total <= 0:
        return 0.0
    ceiling = min(0.995, target_xrp_ratio + max(0.0, overshoot_slack))
    return max(0.0, ceiling * total - xrp_balance)


def max_ask_xrp_without_overshoot(
    *,
    xrp_balance: float,
    rlusd_balance: float,
    mid_price: float,
    target_xrp_ratio: float,
    xrp_reserve: float,
    overshoot_slack: float,
) -> float:
    """Max ask size (XRP) so a full fill does not drop below target - slack."""
    total = portfolio_xrp_equiv(xrp_balance, rlusd_balance, mid_price)
    if total <= 0:
        return 0.0
    floor = max(0.005, target_xrp_ratio - max(0.0, overshoot_slack))
    spendable = max(0.0, xrp_balance - xrp_reserve)
    return max(0.0, min(spendable, xrp_balance - floor * total))


def cap_leg_size_for_inventory(
    *,
    side: str,
    size_xrp: float,
    xrp_balance: float,
    rlusd_balance: float,
    mid_price: float,
    target_xrp_ratio: float,
    xrp_reserve: float,
    inventory_mode: str,
    overshoot_slack: float,
    pause_bids: bool,
    pause_asks: bool,
    min_size: float,
) -> float:
    """
    Shrink a quote leg so one fill cannot swing inventory past target.

    Rebalance one-sided legs use zero slack (stop at target). Market-make caps
    the vulnerable leg once skew exceeds 8% so a fill cannot deepen the imbalance.
    """
    if size_xrp <= 0 or mid_price <= 0:
        return size_xrp

    total = portfolio_xrp_equiv(xrp_balance, rlusd_balance, mid_price)
    if total <= 0:
        return size_xrp

    deviation = xrp_balance / total - target_xrp_ratio
    mode_rebalance = (inventory_mode or INVENTORY_MODE_MARKET_MAKE).strip().lower() == INVENTORY_MODE_REBALANCE
    one_sided_bid = pause_asks and not pause_bids
    one_sided_ask = pause_bids and not pause_asks
    xrp_heavy = deviation > 0.08
    rlusd_heavy = deviation < -0.08

    if side == "bid":
        if not one_sided_bid and abs(deviation) <= 0.06 and not xrp_heavy:
            return size_xrp
        if deviation >= 0 and not one_sided_bid and not xrp_heavy:
            return size_xrp
        slack = 0.0 if one_sided_bid or xrp_heavy else max(0.0, float(overshoot_slack))
        cap = max_bid_xrp_without_overshoot(
            xrp_balance=xrp_balance,
            rlusd_balance=rlusd_balance,
            mid_price=mid_price,
            target_xrp_ratio=target_xrp_ratio,
            overshoot_slack=slack,
        )
    elif side == "ask":
        if not one_sided_ask and abs(deviation) <= 0.06 and not rlusd_heavy:
            return size_xrp
        if deviation <= 0 and not one_sided_ask and not rlusd_heavy:
            return size_xrp
        slack = 0.0 if one_sided_ask or rlusd_heavy else max(0.0, float(overshoot_slack))
        cap = max_ask_xrp_without_overshoot(
            xrp_balance=xrp_balance,
            rlusd_balance=rlusd_balance,
            mid_price=mid_price,
            target_xrp_ratio=target_xrp_ratio,
            xrp_reserve=xrp_reserve,
            overshoot_slack=slack,
        )
    else:
        return size_xrp

    if cap < min_size:
        return 0.0
    return min(size_xrp, cap)
