"""Edge and toxicity gates — no L1 touch when pickoff risk dominates."""

from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from strategy.fill_quality import FillQualityState
from strategy.quote_decision import assess_inventory, build_quote_adjustments


def test_toxicity_gate_blocks_touch_at_20pct() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.30,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=130.0,
        rlusd_balance=100.0,
        mid_price=1.235,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    fq = FillQualityState(
        recent_fills=10,
        toxic_ratio=0.25,
        toxic_ratio_30s=0.25,
        size_multiplier=0.75,
        spread_multiplier=1.12,
        summary="mixed",
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.16,
        book_spread_pct=0.30,
        depth_imbalance=0.0,
        min_edge_pct=0.12,
        fill_quality=fq,
        inventory_mode="market_make",
    )
    assert not adj.join_touch
    assert adj.touch_mode == "off"
    assert "no touch" in adj.decision_summary.casefold()


def test_mild_rising_momentum_pauses_bids_in_mm() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.05,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=130.0,
        rlusd_balance=100.0,
        mid_price=1.235,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.08,
        effective_spread_l1_pct=0.16,
        book_spread_pct=0.05,
        depth_imbalance=0.0,
        min_edge_pct=0.12,
        inventory_mode="market_make",
    )
    assert adj.pause_bids
    assert "pause bids" in adj.decision_summary
