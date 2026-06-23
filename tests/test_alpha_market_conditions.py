"""Tests for market conditions HUD payload."""

from __future__ import annotations

from datetime import datetime, timezone

from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.ledger.market_conditions import build_market_conditions
from alpha.types import BookLevel, LiquidityDepth, OrderBookSnapshot
from config.settings import BotConfig


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=(BookLevel(price=1.10, size_xrp=5000.0), BookLevel(price=1.09, size_xrp=3000.0)),
        asks=(BookLevel(price=1.11, size_xrp=4000.0), BookLevel(price=1.12, size_xrp=2000.0)),
        best_bid=1.10,
        best_ask=1.11,
        mid=1.105,
        spread=0.01,
        spread_pct=0.90,
        fetched_utc=datetime.now(tz=timezone.utc),
    )


def test_market_conditions_depth_and_sizes() -> None:
    cfg = BotConfig(
        alpha_cycle_interval_seconds=15,
        alpha_base_order_size_xrp=50.0,
        min_order_size_xrp=1.0,
        alpha_risk_per_trade_pct=0.5,
    )
    book = _book()
    liquidity = LiquidityDepth(
        max_slippage_pct=0.5,
        bid_depth_xrp=5000.0,
        ask_depth_xrp=4000.0,
        best_bid=1.10,
        best_ask=1.11,
        mid=1.105,
        spread_pct=0.90,
    )
    ta = TechnicalAnalysisSnapshot(
        mid=1.105,
        enabled=True,
        buy_score=2.0,
        sell_score=1.0,
        breakout_score=0.0,
        bias="bullish",
        entry_buy_allowed=True,
        entry_sell_allowed=False,
        breakout_confirmed=False,
        summary="test",
    )
    mc = build_market_conditions(
        book=book,
        liquidity=liquidity,
        config=cfg,
        portfolio_xrp_equiv=400.0,
        ta=ta,
    )
    assert mc["mid"] == 1.105
    assert mc["ask_depth_xrp"] > 0
    assert mc["bid_depth_xrp"] > 0
    assert mc["recommended_max_buy_xrp"] > 0
    assert mc["recommended_max_sell_xrp"] > 0
    assert mc["cycle_interval_seconds"] == 15
    assert mc["ta"]["buy_score"] == 2.0
    assert mc["liquidity_health"] in ("green", "yellow", "red")
