"""Great-MM gap fixes: edge guard, inventory limits, fill economics."""

from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from monitoring.fill_economics import estimate_spread_capture_xrp
from risk.inventory_limits import assess_inventory_limits
from strategy.quote_decision import assess_inventory, build_quote_adjustments


def test_edge_guard_widens_spread_when_thin() -> None:
    assessment = assess_market_conditions(
        volatility_pct=2.5,
        liquidity_score=0.2,
        book_spread_pct=0.08,
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
    assert not adj.join_touch
    assert adj.spread_multiplier > 1.0
    assert "widened spread" in adj.decision_summary


def test_inventory_limit_pauses_bids_when_xrp_heavy() -> None:
    state = assess_inventory_limits(
        xrp_ratio=0.72,
        target_xrp_ratio=0.55,
        max_deviation=0.12,
        inventory_mode="rebalance",
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


def test_tight_spread_steps_off_touch_when_book_thinner_than_edge() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.044,
        active_profile="tight_spread",
    )
    inv = assess_inventory(
        xrp_balance=103.0,
        rlusd_balance=174.0,
        mid_price=1.337,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    adj = build_quote_adjustments(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.116,
        book_spread_pct=0.044,
        depth_imbalance=-0.7,
        min_edge_pct=0.08,
        inventory_mode="market_make",
    )
    assert adj.join_touch
    assert adj.touch_mode == "near_touch"
    assert "near-touch" in adj.decision_summary


def test_safe_near_touch_on_thin_book_without_full_edge() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.044,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=103.0,
        rlusd_balance=174.0,
        mid_price=1.337,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.16,
        book_spread_pct=0.044,
        depth_imbalance=0.0,
        min_edge_pct=0.12,
    )
    assert adj.join_touch
    assert adj.touch_mode == "near_touch"
    assert "near-touch" in adj.decision_summary


def test_safe_joins_touch_when_book_pays_edge() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
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
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.16,
        book_spread_pct=0.30,
        depth_imbalance=0.0,
        min_edge_pct=0.12,
        inventory_mode="market_make",
    )
    assert adj.join_touch is True
    assert adj.touch_mode == "at_touch"
    assert "at touch" in adj.decision_summary.casefold()


def test_high_volatility_steps_off_touch_on_thin_book() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.044,
        active_profile="high_volatility",
    )
    inv = assess_inventory(
        xrp_balance=103.0,
        rlusd_balance=174.0,
        mid_price=1.337,
        target_xrp_ratio=0.55,
        skew_strength=1.30,
    )
    adj = build_quote_adjustments(
        profile=get_profile("high_volatility"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.20,
        book_spread_pct=0.044,
        depth_imbalance=0.0,
        min_edge_pct=0.13,
    )
    assert adj.join_touch
    assert adj.touch_mode == "near_touch"
    assert "near-touch" in adj.decision_summary


def test_rebalance_rlusd_heavy_bids_at_touch() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.95,
        book_spread_pct=0.07,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=91.0,
        rlusd_balance=190.0,
        mid_price=1.347,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.15,
        book_spread_pct=0.07,
        depth_imbalance=0.0,
        min_edge_pct=0.07,
        target_xrp_ratio=0.55,
        inventory_max_deviation=0.12,
        inventory_mode="rebalance",
    )
    assert adj.pause_asks
    assert not adj.pause_bids
    assert adj.join_touch
    assert adj.touch_backoff_pct == 0.0
    assert "rebalance → bid at touch" in adj.decision_summary


def test_rising_xrp_does_not_pause_rebalance_bids() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.95,
        book_spread_pct=0.07,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=91.0,
        rlusd_balance=190.0,
        mid_price=1.347,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.15,
        effective_spread_l1_pct=0.15,
        book_spread_pct=0.07,
        depth_imbalance=0.0,
        min_edge_pct=0.07,
        target_xrp_ratio=0.55,
        inventory_max_deviation=0.12,
        inventory_mode="rebalance",
    )
    assert adj.pause_asks
    assert not adj.pause_bids
    assert adj.join_touch
    assert "rebalance keeps bid at touch" in adj.decision_summary
