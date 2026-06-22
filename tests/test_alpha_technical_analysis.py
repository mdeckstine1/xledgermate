"""Tests for Alpha technical analysis module."""

from __future__ import annotations

from alpha.decision.engine import DecisionAction, DecisionEngine
from config.settings import BotConfig
from alpha.decision.ta_config import AlphaTechnicalAnalysisConfig, merge_ta_config
from alpha.decision.technical_analysis import TechnicalAnalysis, mids_to_candles
from alpha.types import (
    BalanceSnapshot,
    BookLevel,
    InventorySnapshot,
    LiquidityDepth,
    OrderBookSnapshot,
    RiskSnapshot,
    utc_now,
)


def _rising_mids(n: int = 80, start: float = 1.10, step: float = 0.001) -> list[float]:
    return [start + i * step for i in range(n)]


def test_ta_config_merge_nested():
    base = AlphaTechnicalAnalysisConfig()
    merged = merge_ta_config(base, {"enabled": True, "rsi": {"period": 21, "oversold": 25}})
    assert merged.enabled is True
    assert merged.rsi.period == 21
    assert merged.rsi.oversold == 25


def test_technical_analysis_disabled():
    cfg = BotConfig()
    ta = TechnicalAnalysis(cfg)
    snap = ta.analyze(_rising_mids(), mid=1.18)
    assert snap.enabled is False
    assert snap.entry_buy_allowed is True


def test_technical_analysis_bullish_trend_scores():
    cfg = BotConfig()
    cfg.alpha_technical_analysis.enabled = True
    cfg.alpha_technical_analysis.min_buy_score = 0.5
    cfg.alpha_technical_analysis.min_candles = 10
    cfg.alpha_technical_analysis.candle_bucket_samples = 3
    ta = TechnicalAnalysis(cfg)
    snap = ta.analyze(_rising_mids(90), mid=1.189)
    assert snap.enabled is True
    assert snap.buy_score >= 0.5
    assert len(snap.signals) > 0


def test_mids_to_candles_buckets():
    candles = mids_to_candles(_rising_mids(12), bucket=4)
    assert len(candles) == 3
    assert candles[-1].close > candles[0].open


def test_decision_engine_ta_blocks_buy_when_score_low():
    cfg = BotConfig()
    cfg.alpha_technical_analysis.enabled = True
    cfg.alpha_technical_analysis.min_buy_score = 99.0
    cfg.alpha_technical_analysis.min_candles = 10
    from alpha.inventory.manager import InventoryManager

    cfg.alpha_weakness_deviation = 0.05
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    inventory = InventorySnapshot(
        xrp_ratio=0.40,
        target_xrp_ratio=0.55,
        deviation=-0.15,
        label="rlusd_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="weak",
        portfolio_xrp_equiv=100.0,
    )
    risk = RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="ok",
        trading_allowed=True,
    )
    book = OrderBookSnapshot(
        bids=(BookLevel(1.18, 100.0),),
        asks=(BookLevel(1.19, 100.0),),
        best_bid=1.18,
        best_ask=1.19,
        mid=1.185,
        spread=0.01,
        spread_pct=0.84,
        fetched_utc=utc_now(),
    )
    liquidity = LiquidityDepth(
        max_slippage_pct=0.5,
        ask_depth_xrp=500.0,
        bid_depth_xrp=500.0,
        best_bid=1.18,
        best_ask=1.19,
        mid=1.185,
        spread_pct=0.84,
    )
    ta = TechnicalAnalysis(cfg).analyze(_rising_mids(), mid=1.185)
    result = engine.evaluate(
        inventory=inventory,
        risk=risk,
        book=book,
        liquidity=liquidity,
        balances=BalanceSnapshot(xrp=40, rlusd=70, mid_rlusd_per_xrp=1.185, portfolio_xrp_equiv=100),
        ta=ta,
    )
    assert result.action == DecisionAction.HOLD
    assert "ta_buy_blocked" in result.reason
