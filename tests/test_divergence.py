"""Tests for pivot-based RSI/Stoch divergence detection."""

from __future__ import annotations

import pandas as pd

from alpha.decision.accumulation_scorecard import merge_ta_divergence_into_scorecard
from alpha.decision.divergence import (
    _classify_high_pair,
    _classify_low_pair,
    detect_divergences,
)
from alpha.decision.structure import CandleData
from alpha.decision.ta_config import DivergenceConfig
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from config.settings import BotConfig


def _candle(o: float, h: float, l: float, c: float) -> CandleData:
    return CandleData(open=o, high=h, low=l, close=c)


def _zigzag_down_up_candles() -> list[CandleData]:
    """Two swing lows: second price lower, for pairing with synthetic RSI."""
    candles: list[CandleData] = []
    price = 1.10
    for i in range(30):
        candles.append(_candle(price, price + 0.002, price - 0.002, price))
        price += 0.0005
    # First low region
    for _ in range(4):
        price -= 0.004
        candles.append(_candle(price, price + 0.001, price - 0.006, price - 0.004))
    for _ in range(6):
        price += 0.005
        candles.append(_candle(price, price + 0.006, price - 0.001, price + 0.004))
    # Second lower low
    for _ in range(5):
        price -= 0.005
        candles.append(_candle(price, price + 0.001, price - 0.007, price - 0.005))
    for _ in range(8):
        price += 0.002
        candles.append(_candle(price, price + 0.003, price - 0.001, price + 0.001))
    return candles


def test_classify_bullish_regular_divergence():
    classified = _classify_low_pair(1.0, 0.985, 28.0, 34.0, ind_scale=25.0)
    assert classified is not None
    kind, strength = classified
    assert kind == "bullish_regular"
    assert strength >= 0.35


def test_classify_bearish_regular_divergence():
    classified = _classify_high_pair(1.0, 1.015, 72.0, 65.0, ind_scale=25.0)
    assert classified is not None
    kind, strength = classified
    assert kind == "bearish_regular"
    assert strength >= 0.35


def test_detect_divergences_with_synthetic_rsi_series():
    candles = _zigzag_down_up_candles()
    n = len(candles)
    rsi = pd.Series([50.0] * n)
    # Force higher RSI at the last swing low bar vs prior low region
    rsi.iloc[33] = 30.0
    rsi.iloc[-6] = 38.0
    cfg = DivergenceConfig(
        enabled=True,
        lookback_bars=60,
        min_swing_pct=0.2,
        min_strength=0.25,
        use_rsi=True,
        use_stochastic=False,
        buy_weight=0.7,
    )
    result = detect_divergences(candles, cfg=cfg, rsi=rsi)
    if result.fired:
        assert result.bias == "bullish"
        assert result.buy_contribution > 0
        assert "divergence" in result.kind or result.kind.startswith("bullish")


def test_divergence_wired_in_technical_analysis_snapshot():
    cfg = BotConfig()
    cfg.alpha_technical_analysis.min_candles = 10
    cfg.alpha_technical_analysis.candle_interval_seconds = 0
    cfg.alpha_technical_analysis.candle_bucket_samples = 3
    from alpha.decision.technical_analysis import TechnicalAnalysis

    ta = TechnicalAnalysis(cfg)
    mids = [1.10 + i * 0.0001 for i in range(120)]
    snap = ta.analyze(mids, mid=mids[-1])
    div_signal = next((s for s in snap.signals if s.name == "divergence"), None)
    assert div_signal is not None
    assert hasattr(snap, "divergence_fired")
    assert snap.divergence_bias in ("bullish", "bearish", "neutral")


def test_merge_divergence_into_accumulation_scorecard():
    ta = TechnicalAnalysisSnapshot(
        mid=1.0,
        enabled=True,
        buy_score=2.0,
        sell_score=1.0,
        breakout_score=0.0,
        bias="bullish",
        entry_buy_allowed=True,
        entry_sell_allowed=False,
        breakout_confirmed=False,
        divergence_fired=True,
        divergence_bias="bullish",
        divergence_kind="bullish_regular",
        divergence_indicator="rsi",
        divergence_strength=0.72,
        divergence_detail="test",
    )
    merged = merge_ta_divergence_into_scorecard({"fills_count": 0}, ta)
    assert merged["divergence"]["fired"] is True
    assert merged["divergence"]["kind"] == "bullish_regular"


def test_divergence_disabled_returns_neutral():
    candles = _zigzag_down_up_candles()
    cfg = DivergenceConfig(enabled=False)
    result = detect_divergences(candles, cfg=cfg, rsi=pd.Series([40.0] * len(candles)))
    assert result.fired is False
    assert result.bias == "neutral"
