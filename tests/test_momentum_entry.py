"""Tests for bull-run / breakout momentum entries."""

from __future__ import annotations

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.decision.momentum_entry import evaluate_bull_run_entry
from alpha.decision.structure import MarketStructureSnapshot
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
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


def test_bull_run_active_on_breakout_when_balanced():
    cfg = BotConfig(alpha_bull_run_enabled=True)
    snap = evaluate_bull_run_entry(
        cfg,
        inventory=_inventory_balanced(),
        mid=1.05,
        structure=_structure_breakout(),
        ta=None,
    )
    assert snap.active is True
    assert snap.mode == "bull_run"
    assert "breakout_up" in snap.reason


def test_bull_run_blocked_when_too_xrp_heavy():
    cfg = BotConfig(alpha_bull_run_enabled=True, alpha_bull_run_max_deviation=0.02)
    inv = InventorySnapshot(
        xrp_ratio=0.85,
        target_xrp_ratio=0.80,
        deviation=0.05,
        label="xrp_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=600.0,
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )
    snap = evaluate_bull_run_entry(
        cfg,
        inventory=inv,
        mid=1.05,
        structure=_structure_breakout(),
        ta=None,
    )
    assert snap.active is False


def test_engine_place_bid_bull_run_when_balanced():
    cfg = BotConfig(
        alpha_bull_run_enabled=True,
        alpha_reentry_enabled=False,
        alpha_weakness_deviation=0.02,
    )
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    risk = RiskSnapshot(
        trading_allowed=True,
        kill_switch_active=False,
        kill_switch_reason="",
        preflight_ready=True,
        preflight_summary="ok",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        session_pnl_xrp=10.0,
    )
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
    result = engine.evaluate(
        inventory=_inventory_balanced(),
        risk=risk,
        book=book,
        liquidity=LiquidityDepth(
            max_slippage_pct=0.5,
            ask_depth_xrp=5000.0,
            bid_depth_xrp=5000.0,
            best_bid=1.049,
            best_ask=1.051,
            mid=1.05,
            spread_pct=0.19,
        ),
        balances=BalanceSnapshot(
            xrp=400.0,
            rlusd=200.0,
            mid_rlusd_per_xrp=1.05,
            portfolio_xrp_equiv=600.0,
        ),
        structure=_structure_breakout(),
        ta=TechnicalAnalysisSnapshot(
            mid=1.05,
            enabled=True,
            buy_score=2.0,
            sell_score=2.5,
            breakout_score=2.0,
            bias="bullish",
            entry_buy_allowed=True,
            entry_sell_allowed=False,
            breakout_confirmed=True,
            signals=(),
            summary="breakout",
            rsi=55.0,
            stoch_k=60.0,
            stoch_d=55.0,
            bb_upper=1.06,
            bb_middle=1.05,
            bb_lower=1.04,
            bb_bandwidth_pct=0.2,
            fib_levels={},
            elliott_bias="impulse_up",
        ),
    )
    assert result.action == DecisionAction.PLACE_BID
    assert "bull_run" in result.reason
