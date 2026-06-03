"""Near-touch quoting on thin books — visible queue without blind L1 pickoff."""

from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from strategy.quote_decision import assess_inventory, build_quote_adjustments


def test_safe_near_touch_on_6bp_book() -> None:
    """Matches live pilot: ~0.06% book, safe 0.12% edge → backoff ~9%, not 50bps off book."""
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.92,
        book_spread_pct=0.061,
        active_profile="safe",
    )
    inv = assess_inventory(
        xrp_balance=128.0,
        rlusd_balance=138.0,
        mid_price=1.2316,
        target_xrp_ratio=0.55,
        skew_strength=1.45,
    )
    adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=-0.15,
        effective_spread_l1_pct=0.19,
        book_spread_pct=0.061,
        depth_imbalance=-0.29,
        min_edge_pct=0.12,
        inventory_mode="market_make",
    )
    assert adj.join_touch is True
    assert adj.touch_mode == "near_touch"
    assert 0.02 <= adj.touch_backoff_pct <= 0.12
    assert adj.quoting_policy_label.startswith("Policy: near-touch")
    assert "near-touch" in adj.decision_summary
