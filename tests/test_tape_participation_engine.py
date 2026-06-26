"""Engine buy path with tape participation waiver."""

from __future__ import annotations

from datetime import datetime, timezone

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.decision.reentry import ReentryGate
from alpha.decision.structure import MarketStructureSnapshot
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
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


def _ta_bearish_uptrend() -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        mid=1.05,
        enabled=True,
        buy_score=2.0,
        sell_score=3.0,
        breakout_score=0.0,
        bias="bearish",
        entry_buy_allowed=False,
        entry_sell_allowed=False,
        breakout_confirmed=False,
        signals=(),
        summary="bearish lag",
        rsi=48.0,
        stoch_k=52.0,
        stoch_d=50.0,
        bb_upper=1.06,
        bb_middle=1.05,
        bb_lower=1.04,
        bb_bandwidth_pct=0.2,
        fib_levels={},
        elliott_bias="impulse_down",
    )


def test_engine_allows_buy_when_tape_participation_waives_bearish_ta():
    cfg = BotConfig(
        alpha_tape_participation_enabled=True,
        alpha_tape_uptrend_drift_pct=0.1,
        alpha_weakness_deviation=0.02,
        alpha_reentry_enabled=False,
    )
    engine = DecisionEngine(cfg)
    inventory = InventorySnapshot(
        xrp_ratio=0.72,
        target_xrp_ratio=0.80,
        deviation=-0.08,
        label="rlusd_heavy",
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=600.0,
    )
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
        bids=(BookLevel(1.049, 1000.0),),
        asks=(BookLevel(1.051, 1000.0),),
        best_bid=1.049,
        best_ask=1.051,
        mid=1.05,
        spread=0.002,
        spread_pct=0.19,
        fetched_utc=utc_now(),
    )
    liquidity = LiquidityDepth(
        max_slippage_pct=0.5,
        ask_depth_xrp=5000.0,
        bid_depth_xrp=5000.0,
        best_bid=1.049,
        best_ask=1.051,
        mid=1.05,
        spread_pct=0.19,
    )
    structure = MarketStructureSnapshot(
        mid=1.05,
        sample_count=20,
        mean_mid=1.048,
        recent_high=1.051,
        recent_low=1.046,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="neutral drift up",
        swing_high=1.051,
    )
    result = engine.evaluate(
        inventory=inventory,
        risk=risk,
        book=book,
        liquidity=liquidity,
        balances=BalanceSnapshot(
            xrp=400.0,
            rlusd=200.0,
            mid_rlusd_per_xrp=1.05,
            portfolio_xrp_equiv=600.0,
        ),
        ta=_ta_bearish_uptrend(),
        structure=structure,
    )
    assert result.action == DecisionAction.PLACE_BID
    assert "ta_buy_blocked" not in result.reason
