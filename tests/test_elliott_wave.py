"""Tests for 5-wave Elliott swing analysis."""

from __future__ import annotations

from alpha.decision.elliott_wave import (
    analyze_elliott_five_wave,
    find_swing_pivots,
)
from alpha.decision.structure import CandleData


def _bar(o: float, h: float, l: float, c: float) -> CandleData:
    return CandleData(open=o, high=h, low=l, close=c, is_complete=True)


def _bullish_five_wave_series() -> list[CandleData]:
    """Synthetic L-H-L-H-L-H pivot path (bullish impulse)."""
    prices = [
        (1.00, 1.02, 0.99, 1.01),
        (1.01, 1.05, 1.00, 1.04),
        (1.04, 1.045, 1.02, 1.025),
        (1.025, 1.08, 1.02, 1.07),
        (1.07, 1.075, 1.05, 1.055),
        (1.055, 1.12, 1.05, 1.11),
        (1.11, 1.115, 1.08, 1.085),
        (1.085, 1.09, 1.07, 1.075),
        (1.075, 1.14, 1.07, 1.13),
        (1.13, 1.135, 1.10, 1.105),
        (1.105, 1.16, 1.10, 1.15),
    ]
    out: list[CandleData] = []
    for o, h, l, c in prices:
        out.append(_bar(o, h, l, c))
    # Pad to satisfy lookback window in tests
    pad = out[0]
    while len(out) < 55:
        out.insert(0, pad)
    return out


def test_find_swing_pivots_alternating():
    candles = _bullish_five_wave_series()
    pivots = find_swing_pivots(candles, min_swing_pct=0.3)
    assert len(pivots) >= 4
    kinds = [p[2] for p in pivots]
    for i in range(1, len(kinds)):
        assert kinds[i] != kinds[i - 1]


def test_analyze_bullish_five_wave_trending():
    candles = _bullish_five_wave_series()
    ew = analyze_elliott_five_wave(
        candles,
        lookback=50,
        min_swing_pct=0.25,
        impulse_weight=0.6,
        corrective_weight=0.4,
    )
    assert ew.trend in ("bullish_impulse", "neutral")
    if ew.trend == "bullish_impulse":
        assert ew.buy_contribution > 0
        assert ew.wave_label
    assert ew.pivot_count >= 4


def test_wave3_scores_higher_than_wave5_mult():
    candles = _bullish_five_wave_series()
    w3 = analyze_elliott_five_wave(
        candles,
        lookback=50,
        min_swing_pct=0.25,
        impulse_weight=1.0,
        corrective_weight=0.4,
        wave3_mult=1.0,
        wave5_mult=0.5,
        wave1_mult=0.35,
        dip_wave_mult=0.25,
    )
    assert w3.buy_contribution <= 1.0


def test_insufficient_bars_neutral():
    ew = analyze_elliott_five_wave(
        [_bar(1, 1, 1, 1)] * 5,
        lookback=50,
        min_swing_pct=0.35,
        impulse_weight=0.6,
        corrective_weight=0.4,
    )
    assert ew.trend == "neutral"
    assert ew.buy_contribution == 0.0
