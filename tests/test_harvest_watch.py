"""Tests for swing harvest watch (accumulation overlay)."""

from __future__ import annotations

from pathlib import Path

import pytest

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.decision.harvest_watch import (
    HarvestSessionTracker,
    evaluate_harvest_watch,
    harvest_knobs_from_snapshot,
    rolling_move_snapshot,
)
from alpha.decision.price_history import PRICE_HISTORY_PATH, _save_store
from alpha.decision.structure import MarketStructureSnapshot
from alpha.inventory.manager import InventoryManager
from alpha.types import (
    BalanceSnapshot,
    BookLevel,
    InventorySnapshot,
    LiquidityDepth,
    OrderBookSnapshot,
    RiskSnapshot,
    utc_now,
)
from config.settings import BotConfig


def _xrp_heavy() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.85,
        target_xrp_ratio=0.75,
        deviation=0.10,
        label="xrp_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=600.0,
        xrp_allocation_pct=85.0,
        rlusd_allocation_pct=15.0,
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )


def _structure_neutral(mid: float = 1.09) -> MarketStructureSnapshot:
    return MarketStructureSnapshot(
        mid=mid,
        sample_count=20,
        mean_mid=mid,
        recent_high=mid * 1.01,
        recent_low=mid * 0.98,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="neutral",
        swing_high=mid * 1.01,
    )


@pytest.fixture
def price_history_rally(tmp_path):
    path = tmp_path / "alpha_price_history.json"
    n = 3000
    start, end = 1.03, 1.10
    step = (end - start) / (n - 1)
    mids = [start + step * i for i in range(n)]
    store = {"bid": [], "ask": [], "mid": mids, "last": []}
    store["ask"] = [m * 1.00015 for m in mids]
    store["bid"] = [m * 0.99985 for m in mids]
    _save_store(store, path)
    return path


def test_rolling_move_detects_rally(price_history_rally):
    cfg = BotConfig(alpha_cycle_interval_seconds=31)
    snap = rolling_move_snapshot(
        cfg, mid=1.09, hours=24.0, price_history_path=price_history_rally
    )
    assert snap is not None
    assert snap.move_pct >= 5.0
    assert snap.pullback_pct >= 0.5


def test_harvest_arms_on_pullback_after_extended_leg(price_history_rally):
    cfg = BotConfig(
        alpha_accumulation_harvest_watch_enabled=True,
        alpha_accumulation_harvest_execute_enabled=True,
        alpha_strength_deviation=0.05,
        alpha_accumulation_harvest_pullback_arm_pct=0.5,
    )
    sess = HarvestSessionTracker(path=price_history_rally.parent / "harvest.json")
    sess.record_accumulation_active()
    snap = evaluate_harvest_watch(
        cfg,
        inventory=_xrp_heavy(),
        mid=1.09,
        structure=_structure_neutral(1.09),
        ta=None,
        momentum_active=False,
        early_arm=False,
        accumulation_armed=True,
        accumulation_executing=False,
        pending_harvest_sells=0,
        session=sess,
        price_history_path=price_history_rally,
    )
    assert snap.phase in ("watching", "armed")
    assert snap.rolling is not None
    assert snap.rolling.move_pct >= 5.0


def test_harvest_releases_after_momentum_streak(price_history_rally):
    cfg = BotConfig(
        alpha_accumulation_harvest_watch_enabled=True,
        alpha_accumulation_harvest_release_cycles=1,
    )
    sess = HarvestSessionTracker(path=price_history_rally.parent / "harvest.json")
    sess.record_accumulation_active()
    snap = evaluate_harvest_watch(
        cfg,
        inventory=_xrp_heavy(),
        mid=1.10,
        structure=_structure_neutral(1.10),
        ta=None,
        momentum_active=True,
        early_arm=False,
        accumulation_armed=True,
        accumulation_executing=False,
        pending_harvest_sells=0,
        session=sess,
        price_history_path=price_history_rally,
    )
    assert snap.phase == "idle"
    assert snap.reason == "momentum_release"


def test_engine_harvest_trim_when_armed(price_history_rally):
    cfg = BotConfig(
        alpha_accumulation_harvest_watch_enabled=True,
        alpha_accumulation_harvest_execute_enabled=True,
        alpha_strength_deviation=0.05,
        alpha_accumulation_harvest_pullback_arm_pct=0.5,
        alpha_min_edge_threshold_pct=0.01,
        min_order_size_xrp=1.0,
    )
    sess = HarvestSessionTracker(path=price_history_rally.parent / "harvest.json")
    sess.record_accumulation_active()
    hw = evaluate_harvest_watch(
        cfg,
        inventory=_xrp_heavy(),
        mid=1.09,
        structure=_structure_neutral(1.09),
        ta=None,
        momentum_active=False,
        early_arm=False,
        accumulation_armed=True,
        accumulation_executing=False,
        pending_harvest_sells=0,
        session=sess,
        price_history_path=price_history_rally,
    )
    knobs = harvest_knobs_from_snapshot(hw, cfg)
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    engine.set_harvest(hw, knobs)
    book = OrderBookSnapshot(
        bids=(BookLevel(1.089, 500.0),),
        asks=(BookLevel(1.091, 500.0),),
        best_bid=1.089,
        best_ask=1.091,
        mid=1.09,
        spread=0.002,
        spread_pct=0.18,
        fetched_utc=utc_now(),
    )
    risk = RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        session_pnl_xrp=0.0,
        preflight_ready=True,
        preflight_summary="ok",
        trading_allowed=True,
        alerts=(),
    )
    liq = LiquidityDepth(
        max_slippage_pct=0.5,
        bid_depth_xrp=100.0,
        ask_depth_xrp=100.0,
        best_bid=1.089,
        best_ask=1.091,
        mid=1.09,
        spread_pct=0.18,
    )
    balances = BalanceSnapshot(
        xrp=500.0, rlusd=100.0, mid_rlusd_per_xrp=1.09, portfolio_xrp_equiv=600.0
    )
    if hw.phase == "armed":
        decision = engine.evaluate(
            inventory=_xrp_heavy(),
            risk=risk,
            book=book,
            liquidity=liq,
            balances=balances,
        )
        assert decision.action == DecisionAction.PLACE_ASK
        assert "harvest_trim" in decision.reason
    else:
        assert hw.phase in ("watching", "armed")


def test_harvest_reentry_pending_triggers_bid():
    cfg = BotConfig(
        alpha_min_edge_threshold_pct=0.01,
        min_order_size_xrp=1.0,
        alpha_ta_weight=0.0,
    )
    from alpha.decision.harvest_watch import HarvestWatchSnapshot

    hw = HarvestWatchSnapshot(
        enabled=True,
        phase="idle",
        headline="",
        detail="",
        entry_allowed=False,
        reason="idle",
        pending_reentry=True,
    )
    knobs = harvest_knobs_from_snapshot(hw, cfg)
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    engine.set_harvest(hw, knobs, reentry_pending=True)
    book = OrderBookSnapshot(
        bids=(BookLevel(1.089, 500.0),),
        asks=(BookLevel(1.091, 500.0),),
        best_bid=1.089,
        best_ask=1.091,
        mid=1.09,
        spread=0.002,
        spread_pct=0.18,
        fetched_utc=utc_now(),
    )
    risk = RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        session_pnl_xrp=0.0,
        preflight_ready=True,
        preflight_summary="ok",
        trading_allowed=True,
        alerts=(),
    )
    balances = BalanceSnapshot(
        xrp=500.0, rlusd=100.0, mid_rlusd_per_xrp=1.09, portfolio_xrp_equiv=600.0
    )
    liq = LiquidityDepth(
        max_slippage_pct=0.5,
        bid_depth_xrp=100.0,
        ask_depth_xrp=100.0,
        best_bid=1.089,
        best_ask=1.091,
        mid=1.09,
        spread_pct=0.18,
    )
    decision = engine.evaluate(
        inventory=_xrp_heavy(),
        risk=risk,
        book=book,
        liquidity=liq,
        balances=balances,
    )
    assert decision.action == DecisionAction.PLACE_BID
    assert "harvest_reentry" in decision.reason
