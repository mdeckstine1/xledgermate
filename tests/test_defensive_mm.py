"""Defensive market-making strategy modules."""

from core.perception import get_profile, profile_min_edge_pct
from strategy.fill_quality import FillQualityTracker
from strategy.inventory_balance import assess_rebalance_need
from strategy.market_microstructure import (
    assess_book_pressure,
    assess_market_edge,
    classify_momentum,
    resolve_effective_min_edge_pct,
)
from strategy.quote_decision import assess_inventory, build_quote_adjustments
from core.market_conditions import assess_market_conditions


def test_continuous_inventory_skew_when_slightly_xrp_heavy() -> None:
    profile = get_profile("safe")
    inv = assess_inventory(
        xrp_balance=120.0,
        rlusd_balance=60.0,
        mid_price=1.32,
        target_xrp_ratio=0.55,
        skew_strength=profile.inventory_skew_strength,
    )
    assert inv.label in ("slight_xrp_heavy", "xrp_heavy", "balanced")
    assert inv.bid_size_mult <= 1.0
    assert inv.ask_size_mult >= 1.0


def test_momentum_extreme_pauses_vulnerable_side() -> None:
    tier, _ = classify_momentum(0.55)
    assert tier.name == "extreme"
    assert tier.pause_vulnerable is True


def test_bid_heavy_book_protects_bids() -> None:
    pressure = assess_book_pressure(depth_imbalance=0.35, sensitivity=1.0)
    assert pressure.label == "bid_heavy"
    assert 0 < pressure.bid_spread_add_pct <= 0.35
    assert pressure.bid_size_mult < 1.0


def test_market_edge_rejects_tight_book() -> None:
    edge = assess_market_edge(
        book_spread_pct=0.04,
        our_l1_spread_pct=0.12,
        min_edge_pct=0.08,
    )
    assert edge.met is False


def test_xrp_heavy_two_sided_rebalance_copy() -> None:
    advice = assess_rebalance_need(
        xrp_balance=200.0,
        rlusd_balance=60.0,
        mid_price=1.32,
        target_xrp_ratio=0.55,
        spendable_xrp=180.0,
        xrp_reserve=12.0,
        min_order_xrp=1.0,
        fund_with_xrp_only=False,
    )
    assert advice.label == "xrp_heavy"
    assert "already two-sided" in advice.summary


def test_xrp_only_rebalance_advises_ask_side() -> None:
    advice = assess_rebalance_need(
        xrp_balance=200.0,
        rlusd_balance=0.0,
        mid_price=1.32,
        target_xrp_ratio=0.55,
        spendable_xrp=180.0,
        xrp_reserve=12.0,
        min_order_xrp=1.0,
        fund_with_xrp_only=True,
    )
    assert advice.action == "sell_xrp_via_asks"


def test_fill_quality_penalizes_toxic_sells() -> None:
    tracker = FillQualityTracker()
    tracker.note_fill(side="SELL", xrp_amount=10.0, price=1.32, mid_at_fill=1.32)
    tracker.note_mid(1.325)
    state = tracker.assess()
    assert state.recent_fills == 1
    assert state.size_multiplier < 1.0


def test_profile_min_edge_pct_legacy_profile() -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class LegacyProfile:
        name: str
        min_edge_mult: float = 1.0

    assert profile_min_edge_pct(LegacyProfile(name="tight_spread")) == 0.08


def test_resolve_effective_min_edge_profile_first() -> None:
    profile = get_profile("tight_spread")
    edge, _ = resolve_effective_min_edge_pct(
        profile=profile, edge_strictness=1.0, book_spread_pct=0.07, dynamic_enabled=False
    )
    assert edge == 0.08


def test_resolve_effective_min_edge_dynamic_lowers_on_tight_book() -> None:
    profile = get_profile("safe")
    static, _ = resolve_effective_min_edge_pct(
        profile=profile, edge_strictness=1.0, book_spread_pct=0.07, dynamic_enabled=False
    )
    dynamic, _ = resolve_effective_min_edge_pct(
        profile=profile, edge_strictness=1.0, book_spread_pct=0.07, dynamic_enabled=True
    )
    assert static == 0.12
    assert dynamic < static


def test_profiles_diverge_under_hostile_market() -> None:
    assessment = assess_market_conditions(
        volatility_pct=2.5,
        liquidity_score=0.2,
        book_spread_pct=0.5,
        active_profile="safe",
    )
    safe_adj = build_quote_adjustments(
        profile=get_profile("safe"),
        assessment=assessment,
        inventory=assess_inventory(
            xrp_balance=100.0,
            rlusd_balance=50.0,
            mid_price=1.32,
            target_xrp_ratio=0.55,
            skew_strength=1.0,
        ),
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.20,
        book_spread_pct=0.08,
        depth_imbalance=0.0,
        min_edge_pct=0.08,
    )
    tight_adj = build_quote_adjustments(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        inventory=assess_inventory(
            xrp_balance=100.0,
            rlusd_balance=50.0,
            mid_price=1.32,
            target_xrp_ratio=0.55,
            skew_strength=0.75,
        ),
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.20,
        book_spread_pct=0.08,
        depth_imbalance=0.0,
        min_edge_pct=0.08,
    )
    assert safe_adj.spread_multiplier > tight_adj.spread_multiplier
    assert safe_adj.size_multiplier < tight_adj.size_multiplier


def test_order_manager_hard_gate_on_market_edge_not_met() -> None:
    """Tier 2.5 hard gate: build_quotes must return zero intents when market_edge_met=False.

    This prevents live placement (place_quote) on books that do not offer sufficient
    edge after fees + profile min edge. See P0 in collab THREAD + doc 05.
    """
    from config.settings import BotConfig
    from engine.order_manager import OrderManager
    from strategy.quote_decision import QuoteAdjustments

    # Minimal viable config for the manager (real defaults are fine; we override sizes)
    cfg = BotConfig.load()
    # Ensure we have some size configured
    if not any(s > 0 for s in getattr(cfg, "order_sizes", [0])):
        # fallback for test envs without full yaml
        object.__setattr__(cfg, "order_sizes", [10.0, 8.0])  # type: ignore[attr-defined]
        object.__setattr__(cfg, "order_levels", 2)  # type: ignore[attr-defined]
        object.__setattr__(cfg, "min_order_size_xrp", 1.0)  # type: ignore[attr-defined]
        object.__setattr__(cfg, "base_spread", 0.25)  # type: ignore[attr-defined]

    om = OrderManager(cfg)

    spreads = {1: 0.25, 2: 0.30}
    adj_bad = QuoteAdjustments(market_edge_met=False, market_edge_pct=-0.05)
    plan = om.build_quotes(
        mid_price=0.52,
        spreads_pct=spreads,
        xrp_balance=300.0,
        rlusd_balance=150.0,
        adjustments=adj_bad,
        best_bid=0.521,
        best_ask=0.519,  # crossed-ish but we test the gate first
    )
    assert plan.intents == [], "hard gate must produce zero intents"
    assert "market_edge_met=false" in plan.reason
    assert "hard gate" in plan.reason.lower()

    # Sanity: when edge is met, it can produce intents (assuming balances)
    adj_ok = QuoteAdjustments(market_edge_met=True, market_edge_pct=0.03)
    plan_ok = om.build_quotes(
        mid_price=0.52,
        spreads_pct=spreads,
        xrp_balance=300.0,
        rlusd_balance=150.0,
        adjustments=adj_ok,
    )
    # May still be [] if other guards (pause, size, fund mode), but must not be the edge reason
    if plan_ok.intents:
        assert "market_edge_met=false" not in plan_ok.reason
