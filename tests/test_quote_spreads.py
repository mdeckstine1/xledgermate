"""Spread and inventory skew must stay near the market."""

from core.perception import get_profile
from strategy.quote_decision import (
    QuoteAdjustments,
    apply_spread_adjustments,
    assess_inventory,
)


def test_xrp_heavy_inventory_skew_is_capped() -> None:
    profile = get_profile("tight_spread")
    inv = assess_inventory(
        xrp_balance=200.0,
        rlusd_balance=0.0,
        mid_price=1.32,
        target_xrp_ratio=0.55,
        skew_strength=profile.inventory_skew_strength,
    )
    assert inv.label == "xrp_heavy"
    assert inv.bid_spread_add_pct <= 1.5
    assert inv.ask_spread_add_pct == 0.0


def test_apply_spread_adjustments_does_not_blend_inventory() -> None:
    base = {1: 0.08, 2: 0.12}
    adj = QuoteAdjustments(
        spread_multiplier=1.0,
        bid_spread_add_pct=10.0,
        ask_spread_add_pct=0.0,
    )
    out = apply_spread_adjustments(base, adj)
    assert out[1] == 0.08
    assert out[2] == 0.12


def test_hostile_market_widens_profile_spread_only() -> None:
    base = {1: 0.10}
    adj = QuoteAdjustments(spread_multiplier=1.35)
    out = apply_spread_adjustments(base, adj)
    assert abs(out[1] - 0.135) < 1e-6
