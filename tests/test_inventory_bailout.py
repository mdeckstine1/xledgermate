"""Automatic inventory and toxicity bailout (no manual DEX rebalances)."""

from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from risk.inventory_limits import INVENTORY_MODE_MARKET_MAKE, assess_inventory_limits
from strategy.fill_quality import FillQualityState
from strategy.quote_decision import assess_inventory, build_quote_adjustments


def test_market_make_bails_out_pauses_bids_at_74pct_xrp() -> None:
    """Pilot scenario: ~74% XRP (+19%) must not keep bidding at touch."""
    state = assess_inventory_limits(
        xrp_ratio=0.74,
        target_xrp_ratio=0.55,
        max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
    )
    assert state.pause_bids
    assert not state.pause_asks
    assert "inventory bailout" in state.summary


def test_market_make_mild_skew_stays_two_sided() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.07,
        active_profile="tight_spread",
    )
    inv = assess_inventory(
        xrp_balance=140.0,
        rlusd_balance=120.0,
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
    assert not adj.pause_bids
    assert not adj.pause_asks


def test_market_make_heavy_skew_one_sided_ask_bailout() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.07,
        active_profile="tight_spread",
    )
    inv = assess_inventory(
        xrp_balance=172.0,
        rlusd_balance=82.0,
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
    assert adj.pause_bids and not adj.pause_asks
    assert (
        "near-touch" in adj.decision_summary
        or "off touch" in adj.decision_summary
        or "step off touch" in adj.decision_summary
    )


def test_toxic_bailout_pauses_bids_when_xrp_heavy() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.05,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=168.0,
        rlusd_balance=88.0,
        mid_price=1.337,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    fq = FillQualityState(
        recent_fills=8,
        toxic_fills=2,
        toxic_ratio=0.22,
        toxic_ratio_30s=0.22,
        size_multiplier=0.65,
        spread_multiplier=1.15,
        summary="Fill quality stressed",
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=-0.08,
        effective_spread_l1_pct=0.14,
        book_spread_pct=0.05,
        depth_imbalance=-0.5,
        min_edge_pct=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
        fill_quality=fq,
    )
    assert adj.pause_bids
    assert (
        "toxicity bailout" in adj.decision_summary
        or "inventory bailout" in adj.decision_summary
    )
