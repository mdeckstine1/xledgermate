"""Great-MM gap fixes: edge guard, inventory limits, fill economics."""

from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from monitoring.fill_economics import estimate_spread_capture_xrp
from risk.inventory_limits import assess_inventory_limits
from strategy.quote_decision import assess_inventory, build_quote_adjustments


def test_edge_guard_widens_spread_when_thin() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.1,
        liquidity_score=0.6,
        book_spread_pct=0.2,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=100.0,
        rlusd_balance=50.0,
        mid_price=1.32,
        target_xrp_ratio=0.55,
        skew_strength=1.0,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.05,
        book_spread_pct=0.08,
        depth_imbalance=0.0,
        min_edge_pct=0.12,
    )
    assert adj.spread_multiplier > 1.0
    assert "widened spread" in adj.decision_summary


def test_inventory_limit_pauses_bids_when_xrp_heavy() -> None:
    state = assess_inventory_limits(
        xrp_ratio=0.72,
        target_xrp_ratio=0.55,
        max_deviation=0.12,
    )
    assert state.pause_bids
    assert not state.pause_asks


def test_spread_capture_sell_above_mid_positive() -> None:
    profit = estimate_spread_capture_xrp(
        side="SELL",
        xrp_amount=10.0,
        fill_price_rlusd_per_xrp=1.35,
        mid_at_quote_rlusd_per_xrp=1.34,
    )
    assert profit > 0
