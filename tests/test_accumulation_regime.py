"""Tests for accumulation regime — unified bull/breakout RLUSD deployment."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from alpha.decision.accumulation_regime import (
    AccumulationSessionTracker,
    accumulation_knobs_from_snapshot,
    evaluate_accumulation_regime,
)
from alpha.decision.engine import DecisionAction, DecisionEngine
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


def _inventory_balanced() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.795,
        target_xrp_ratio=0.80,
        deviation=-0.005,
        label="balanced",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=600.0,
        xrp_allocation_pct=79.5,
        rlusd_allocation_pct=20.5,
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )


def _structure_breakout() -> MarketStructureSnapshot:
    return MarketStructureSnapshot(
        mid=1.05,
        sample_count=20,
        mean_mid=1.048,
        recent_high=1.049,
        recent_low=1.044,
        trend="bullish",
        breakout_up=True,
        breakout_down=False,
        summary="breakout",
        swing_high=1.049,
    )


def test_accumulation_armed_on_breakout_balanced():
    cfg = BotConfig(alpha_accumulation_regime_enabled=True)
    snap = evaluate_accumulation_regime(
        cfg,
        inventory=_inventory_balanced(),
        mid=1.05,
        structure=_structure_breakout(),
        ta=None,
        operator_market_regime="bull",
        rlusd_balance=500.0,
    )
    assert snap.armed is True
    assert snap.entry_allowed is True
    assert snap.phase == "armed"


def test_accumulation_knobs_tight_chase_when_armed():
    cfg = BotConfig(alpha_accumulation_regime_enabled=True)
    snap = evaluate_accumulation_regime(
        cfg,
        inventory=_inventory_balanced(),
        mid=1.05,
        structure=_structure_breakout(),
        ta=None,
        operator_market_regime="bull",
        rlusd_balance=500.0,
    )
    knobs = accumulation_knobs_from_snapshot(snap, cfg)
    assert knobs.armed is True
    assert knobs.buy_offset_pct == cfg.alpha_accumulation_buy_offset_pct
    assert knobs.max_pending_buys == cfg.alpha_accumulation_max_pending_buys
    assert knobs.stale_drift_pct >= knobs.buy_offset_pct


def test_engine_place_bid_accumulation_when_armed():
    base = BotConfig(
        alpha_accumulation_regime_enabled=True,
        alpha_reentry_enabled=False,
        alpha_risk_per_trade_pct=2.0,
        alpha_accumulation_risk_boost=1.5,
    )
    cfg = replace(
        base,
        alpha_technical_analysis=replace(base.alpha_technical_analysis, enabled=False),
    )

    inv_mgr = InventoryManager(cfg)
    engine = DecisionEngine(cfg, inventory=inv_mgr)
    acc_snap = evaluate_accumulation_regime(
        cfg,
        inventory=_inventory_balanced(),
        mid=1.05,
        structure=_structure_breakout(),
        ta=None,
        operator_market_regime="bull",
        rlusd_balance=500.0,
    )
    knobs = accumulation_knobs_from_snapshot(acc_snap, cfg)
    engine.set_accumulation(acc_snap, knobs)

    book = OrderBookSnapshot(
        bids=(BookLevel(1.049, 5000.0),),
        asks=(BookLevel(1.051, 5000.0),),
        best_bid=1.049,
        best_ask=1.051,
        mid=1.05,
        spread=0.002,
        spread_pct=0.19,
        fetched_utc=utc_now(),
    )
    risk = RiskSnapshot(
        trading_allowed=True,
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=5.0,
        session_pnl_xrp=0.0,
        preflight_ready=True,
        preflight_summary="ok",
        alerts=(),
    )
    balances = BalanceSnapshot(xrp=400.0, rlusd=200.0, mid_rlusd_per_xrp=1.05, portfolio_xrp_equiv=600.0)
    liq = LiquidityDepth(
        max_slippage_pct=0.5,
        ask_depth_xrp=5000.0,
        bid_depth_xrp=5000.0,
        best_bid=1.049,
        best_ask=1.051,
        mid=1.05,
        spread_pct=0.19,
    )

    result = engine.evaluate(
        inventory=_inventory_balanced(),
        risk=risk,
        book=book,
        liquidity=liq,
        pending_buy_count=0,
        balances=balances,
    )
    assert result.action == DecisionAction.PLACE_BID
    assert "accumulation" in result.reason


def test_session_budget_blocks_when_exhausted(tmp_path: Path):
    path = tmp_path / "acc.json"
    session = AccumulationSessionTracker(path=path)
    cfg = BotConfig(alpha_accumulation_rlusd_budget_pct=10.0)
    budget = session.budget_rlusd(cfg, rlusd_balance=1000.0)
    assert budget == 100.0
    session.record_bid(size_xrp=50.0, price_rlusd_per_xrp=2.0)
    assert session.committed_rlusd() == 100.0
    snap = evaluate_accumulation_regime(
        cfg,
        inventory=_inventory_balanced(),
        mid=1.05,
        structure=_structure_breakout(),
        ta=None,
        operator_market_regime="bull",
        rlusd_balance=1000.0,
        session=session,
    )
    assert snap.armed is False
    assert "accumulation_budget_exhausted" in snap.blockers
