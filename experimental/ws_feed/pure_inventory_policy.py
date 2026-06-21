"""
WS pure path — inventory limits + leg caps (parity with sacred order_manager).

Does not change A-S reservation/spread; only sizes and which L1 legs are active.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from risk.inventory_limits import (
    assess_inventory_limits,
    cap_leg_size_for_inventory,
    portfolio_xrp_equiv,
)


@dataclass(frozen=True)
class PureInventoryPolicyResult:
    pause_bids: bool
    pause_asks: bool
    limits_summary: str
    bid_size_xrp: float
    ask_size_xrp: float
    policy_tag: str


def apply_pure_inventory_policy(
    *,
    bid_size_xrp: float,
    ask_size_xrp: float,
    xrp_balance: float,
    rlusd_balance: float,
    mid_price: float,
    target_xrp_ratio: float,
    inventory_max_deviation: float,
    inventory_mode: str,
    xrp_reserve: float,
    inventory_overshoot_slack: float,
    min_order_size_xrp: float,
    bid_size_mult: float,
    ask_size_mult: float,
    apply_side_pauses: bool = True,
) -> PureInventoryPolicyResult:
    """Apply sacred inventory limits and per-leg caps to L1 sizes.

    When apply_side_pauses=False (v2.2.0+ QD path), size caps remain but
    pause_bids/pause_asks do not zero legs — quoting permissions come from QD.
    """
    total = portfolio_xrp_equiv(xrp_balance, rlusd_balance, mid_price)
    ratio = xrp_balance / total if total > 0 else 1.0
    limits = assess_inventory_limits(
        xrp_ratio=ratio,
        target_xrp_ratio=target_xrp_ratio,
        max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
    )

    bid = max(0.0, bid_size_xrp * bid_size_mult)
    ask = max(0.0, ask_size_xrp * ask_size_mult)

    cap_kwargs = dict(
        xrp_balance=xrp_balance,
        rlusd_balance=rlusd_balance,
        mid_price=mid_price,
        target_xrp_ratio=target_xrp_ratio,
        xrp_reserve=xrp_reserve,
        inventory_mode=inventory_mode,
        overshoot_slack=inventory_overshoot_slack,
        pause_bids=limits.pause_bids if apply_side_pauses else False,
        pause_asks=limits.pause_asks if apply_side_pauses else False,
        min_size=min_order_size_xrp,
    )
    bid = cap_leg_size_for_inventory(side="bid", size_xrp=bid, **cap_kwargs)
    ask = cap_leg_size_for_inventory(side="ask", size_xrp=ask, **cap_kwargs)

    if apply_side_pauses and limits.pause_bids:
        bid = 0.0
    if apply_side_pauses and limits.pause_asks:
        ask = 0.0

    tags: List[str] = []
    if limits.summary:
        tags.append(limits.summary)
    if bid_size_mult != 1.0 or ask_size_mult != 1.0:
        tags.append(f"inv-size bid×{bid_size_mult:.2f} ask×{ask_size_mult:.2f}")

    return PureInventoryPolicyResult(
        pause_bids=limits.pause_bids,
        pause_asks=limits.pause_asks,
        limits_summary=limits.summary,
        bid_size_xrp=round(bid, 4),
        ask_size_xrp=round(ask, 4),
        policy_tag="; ".join(tags),
    )


def apply_pause_to_ladder(
    ladder: List[Dict[str, Any]],
    *,
    pause_bids: bool,
    pause_asks: bool,
    min_order_size_xrp: float,
) -> List[Dict[str, Any]]:
    """Deactivate L1 legs for paused sides; drop sub-min sizes."""
    out: List[Dict[str, Any]] = []
    for row in ladder:
        item = dict(row)
        side = str(item.get("side") or "").lower()
        size = float(item.get("size_xrp") or 0)
        if item.get("level") == 1 and item.get("active"):
            if side == "bid" and (pause_bids or size < min_order_size_xrp):
                item["active"] = False
                item["planned"] = True
            if side == "ask" and (pause_asks or size < min_order_size_xrp):
                item["active"] = False
                item["planned"] = True
        out.append(item)
    return out


def count_active_l1_quotes(ladder: List[Dict[str, Any]]) -> int:
    return sum(
        1
        for row in ladder
        if row.get("level") == 1 and row.get("active") and float(row.get("size_xrp") or 0) > 0
    )
