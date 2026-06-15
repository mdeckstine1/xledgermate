"""
B2 — Pure A-S dynamic L1 sizing (WS path only).

L1 = min(configured_l1_xrp, k × XRP balance), then inventory + pressure skew.
Ask boost when XRP-heavy and competitor ask-pressure is low (rebalance on soft book).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_LADDER_SIZE_FRACS = (1.0, 0.6, 0.3)

DEFAULT_BALANCE_FRACTION_K = 0.07
DEFAULT_ASK_BOOST_XRP_HEAVY_LOW_PRESSURE = 1.35
DEFAULT_BID_TRIM_XRP_HEAVY_LOW_PRESSURE = 0.85
LOW_PRESSURE_THRESHOLD = 0.4


@dataclass(frozen=True)
class PureAsSizes:
    l1_xrp: float
    bid_size_xrp: float
    ask_size_xrp: float
    rationale: str


def compute_pure_l1_sizes(
    *,
    xrp_balance: float,
    configured_l1_xrp: float,
    min_order_size_xrp: float = 1.0,
    balance_fraction_k: float = DEFAULT_BALANCE_FRACTION_K,
    inventory_skew: float,
    inventory_label: str = "",
    pressure_size_mult: float = 1.0,
    effective_pressure: Optional[float] = None,
    low_pressure_threshold: float = LOW_PRESSURE_THRESHOLD,
    ask_boost: float = DEFAULT_ASK_BOOST_XRP_HEAVY_LOW_PRESSURE,
    bid_trim: float = DEFAULT_BID_TRIM_XRP_HEAVY_LOW_PRESSURE,
) -> PureAsSizes:
    """Compute L1 bid/ask sizes for the pure WS path."""
    balance_cap = max(min_order_size_xrp, balance_fraction_k * max(xrp_balance, 0.0))
    l1 = round(max(min_order_size_xrp, min(configured_l1_xrp, balance_cap)), 4)

    bid_mult = 1.0 - max(0.0, inventory_skew) * 0.5
    ask_mult = 1.0 + max(0.0, inventory_skew) * 0.5

    bid = l1 * pressure_size_mult * bid_mult
    ask = l1 * pressure_size_mult * ask_mult

    label = (inventory_label or "").lower()
    xrp_heavy = inventory_skew > 0.12 or "xrp_heavy" in label
    low_pressure = effective_pressure is not None and effective_pressure < low_pressure_threshold
    boost_tag = ""
    if xrp_heavy and low_pressure:
        ask *= ask_boost
        bid *= bid_trim
        boost_tag = f" ask-boost×{ask_boost:.2f}(XRP-heavy+low-pressure)"

    bid = max(min_order_size_xrp, round(bid, 4))
    ask = max(min_order_size_xrp, round(ask, 4))

    rationale = (
        f"SIZE L1={l1:.1f}XRP min({configured_l1_xrp:.0f}, {balance_fraction_k:.0%}×bal={balance_cap:.1f}) "
        f"bid={bid:.1f} ask={ask:.1f} pressure_mult={pressure_size_mult:.2f}"
        f"{boost_tag}"
    )
    return PureAsSizes(l1_xrp=l1, bid_size_xrp=bid, ask_size_xrp=ask, rationale=rationale)


def build_pure_quote_ladder(
    *,
    mid: float,
    l1_bid_price: float,
    l1_ask_price: float,
    l1_bid_size: float,
    l1_ask_size: float,
    optimal_spread_pct: float,
    level_spread_increment: float = 0.0003,
    order_levels: int = 3,
    min_order_size_xrp: float = 1.0,
    configured_level_sizes: Optional[Sequence[float]] = None,
    active: bool = True,
) -> List[Dict[str, Any]]:
    """L1 from A-S touch; L2/L3 stepped by spread increment with scaled sizes."""
    half = (optimal_spread_pct / 100.0) / 2.0
    intents: List[Dict[str, Any]] = []
    levels = max(1, min(int(order_levels), len(DEFAULT_LADDER_SIZE_FRACS)))

    for level in range(1, levels + 1):
        extra = (level - 1) * level_spread_increment
        if level == 1:
            bid_price, ask_price = l1_bid_price, l1_ask_price
        else:
            bid_price = mid * (1.0 - half - extra)
            ask_price = mid * (1.0 + half + extra)

        if level == 1:
            bid_size = max(min_order_size_xrp, round(l1_bid_size, 4))
            ask_size = max(min_order_size_xrp, round(l1_ask_size, 4))
        else:
            cfg_size = None
            if configured_level_sizes and len(configured_level_sizes) >= level:
                raw = configured_level_sizes[level - 1]
                if raw and raw > 0:
                    cfg_size = float(raw)
            frac = DEFAULT_LADDER_SIZE_FRACS[level - 1]
            bid_size = max(min_order_size_xrp, round((cfg_size or l1_bid_size * frac), 4))
            ask_size = max(min_order_size_xrp, round((cfg_size or l1_ask_size * frac), 4))

        for side, price, size in (
            ("bid", bid_price, bid_size),
            ("ask", ask_price, ask_size),
        ):
            intents.append(
                {
                    "level": level,
                    "side": side,
                    "price": price,
                    "size_xrp": size,
                    "active": active and level == 1,
                    "planned": not active or level > 1,
                }
            )
    return intents
