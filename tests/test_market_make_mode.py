"""Market-make vs rebalance inventory modes."""

from risk.inventory_limits import (
    INVENTORY_MODE_MARKET_MAKE,
    INVENTORY_MODE_REBALANCE,
    assess_inventory_limits,
)
from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from strategy.quote_decision import assess_inventory, build_quote_adjustments


def test_market_make_bails_out_when_rlusd_heavy() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.07,
        active_profile="tight_spread",
    )
    inv = assess_inventory(
        xrp_balance=91.0,
        rlusd_balance=190.0,
        mid_price=1.347,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    adj = build_quote_adjustments(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.08,
        book_spread_pct=0.07,
        depth_imbalance=0.0,
        min_edge_pct=0.08,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
    )
    assert adj.pause_asks
    assert not adj.pause_bids
    assert "inventory bailout" in adj.decision_summary


def test_market_make_bails_out_when_xrp_heavy() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.07,
        active_profile="tight_spread",
    )
    inv = assess_inventory(
        xrp_balance=162.0,
        rlusd_balance=95.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    adj = build_quote_adjustments(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.08,
        book_spread_pct=0.07,
        depth_imbalance=0.0,
        min_edge_pct=0.08,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
    )
    assert adj.pause_bids
    assert not adj.pause_asks
    assert "inventory bailout" in adj.decision_summary


def test_market_make_shows_bailout_line_on_safe_profile() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.049,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=156.0,
        rlusd_balance=102.0,
        mid_price=1.337,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=-0.12,
        effective_spread_l1_pct=0.238,
        book_spread_pct=0.049,
        depth_imbalance=-0.69,
        min_edge_pct=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
    )
    assert "operating mode: market make" in adj.decision_summary
    assert "MM bailout → asks at touch only" in adj.decision_summary
    assert adj.pause_bids
    assert not adj.pause_asks


def test_rebalance_mode_pauses_side() -> None:
    state = assess_inventory_limits(
        xrp_ratio=0.39,
        target_xrp_ratio=0.55,
        max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_REBALANCE,
    )
    assert state.pause_asks
    assert not state.pause_bids


def test_market_make_bails_out_rlusd_heavy_like_rebalance() -> None:
    state = assess_inventory_limits(
        xrp_ratio=0.39,
        target_xrp_ratio=0.55,
        max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
    )
    assert state.pause_asks
    assert not state.pause_bids
