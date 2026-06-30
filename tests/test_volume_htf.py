"""Tests for volume confirmation and HTF bias filter."""

from __future__ import annotations

from alpha.decision.htf_bias import evaluate_htf_bias, resolve_htf_interval_seconds
from alpha.decision.structure import CandleData
from alpha.decision.ta_config import HtfBiasConfig, VolumeConfirmationConfig
from alpha.decision.volume_confirmation import bar_volume, evaluate_volume_confirmation
from config.settings import BotConfig
from alpha.decision.technical_analysis import TechnicalAnalysis


def _c(o: float, h: float, l: float, c: float, *, vol: float = 10.0, complete: bool = True) -> CandleData:
    return CandleData(open=o, high=h, low=l, close=c, volume=vol, is_complete=complete)


def test_bar_volume_uses_tick_count():
    assert bar_volume(_c(1, 1, 1, 1, vol=42)) == 42.0


def test_volume_spike_bullish():
    candles = [_c(1.0, 1.0, 1.0, 1.0, vol=10) for _ in range(20)]
    candles.append(_c(1.0, 1.01, 0.99, 1.005, vol=30))
    cfg = VolumeConfirmationConfig(
        enabled=True,
        lookback_bars=10,
        min_spike_ratio=1.5,
        buy_weight=0.5,
        breakout_weight=0.8,
    )
    result = evaluate_volume_confirmation(candles, cfg)
    assert result.fired is True
    assert result.bias == "bullish"
    assert result.buy_contribution > 0
    assert result.breakout_contribution > 0


def test_volume_low_activity_dampens():
    candles = [_c(1.0, 1.0, 1.0, 1.0, vol=20) for _ in range(20)]
    candles.append(_c(1.0, 1.001, 0.999, 1.0, vol=5))
    cfg = VolumeConfirmationConfig(enabled=True, lookback_bars=10, low_volume_ratio=0.8)
    result = evaluate_volume_confirmation(candles, cfg)
    assert result.score_dampen < 1.0


def test_htf_bullish_sma_stack():
    candles = []
    price = 1.0
    for _ in range(30):
        price += 0.002
        candles.append(_c(price - 0.001, price + 0.001, price - 0.002, price, vol=10))
    cfg = HtfBiasConfig(enabled=True, min_closed_bars=12, fast_sma=5, slow_sma=10)
    result = evaluate_htf_bias(candles, cfg, interval_seconds=3600)
    assert result.bias == "bullish"
    assert result.buy_multiplier > 1.0
    assert result.sell_multiplier < 1.0


def test_resolve_htf_interval_above_ltf():
    cfg = HtfBiasConfig(interval_seconds=3600)
    assert resolve_htf_interval_seconds(cfg, ltf_interval_seconds=300) == 3600
    assert resolve_htf_interval_seconds(cfg, ltf_interval_seconds=7200) >= 9000


def test_technical_analysis_includes_volume_and_htf_signals():
    cfg = BotConfig()
    cfg.alpha_technical_analysis.min_candles = 5
    cfg.alpha_technical_analysis.candle_interval_seconds = 0
    cfg.alpha_technical_analysis.candle_bucket_samples = 2
    mids = [1.0 + i * 0.001 for i in range(80)]
    ltf = [_c(mids[i], mids[i] + 0.001, mids[i] - 0.001, mids[i + 1], vol=10 + i % 5) for i in range(len(mids) - 1)]
    htf = [_c(1.0 + i * 0.01, 1.01 + i * 0.01, 0.99 + i * 0.01, 1.0 + (i + 1) * 0.01, vol=20) for i in range(25)]
    snap = TechnicalAnalysis(cfg).analyze(mids, mid=mids[-1], candles=ltf, htf_candles=htf, htf_interval_seconds=3600)
    names = {s.name for s in snap.signals}
    assert "volume_confirmation" in names
    assert "htf_bias" in names
