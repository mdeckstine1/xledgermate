"""Tests for live-tape participation waiver."""

from __future__ import annotations

from alpha.decision.structure import MarketStructureSnapshot
from alpha.decision.tape_participation import evaluate_tape_participation
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from config.settings import BotConfig


def _structure(**kwargs) -> MarketStructureSnapshot:
    base = dict(
        mid=1.05,
        sample_count=20,
        mean_mid=1.048,
        recent_high=1.051,
        recent_low=1.046,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="test",
        swing_high=1.051,
    )
    base.update(kwargs)
    return MarketStructureSnapshot(**base)


def _ta(**kwargs) -> TechnicalAnalysisSnapshot:
    base = dict(
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
        summary="test",
        rsi=45.0,
        stoch_k=55.0,
        stoch_d=50.0,
        bb_upper=1.06,
        bb_middle=1.05,
        bb_lower=1.04,
        bb_bandwidth_pct=0.2,
        fib_levels={},
        elliott_bias="impulse_down",
    )
    base.update(kwargs)
    return TechnicalAnalysisSnapshot(**base)


def test_participation_waives_when_drift_and_bearish_ta():
    cfg = BotConfig(alpha_tape_participation_enabled=True, alpha_tape_uptrend_drift_pct=0.1)
    snap = evaluate_tape_participation(
        cfg,
        mid=1.05,
        structure=_structure(mean_mid=1.048, trend="neutral"),
        ta=_ta(bias="bearish", buy_score=2.0, sell_score=3.0),
    )
    assert snap.active is True
    assert "uptrend_waiver" in snap.reason


def test_participation_waives_when_recovering_toward_mean():
    cfg = BotConfig(alpha_tape_participation_enabled=True, alpha_tape_near_mean_pct=0.35)
    snap = evaluate_tape_participation(
        cfg,
        mid=1.0455,
        structure=_structure(mean_mid=1.0478, recent_low=1.044, trend="neutral"),
        ta=_ta(bias="bearish", buy_score=2.0, sell_score=3.0),
    )
    assert snap.active is True
    assert "uptrend_waiver" in snap.reason


def test_participation_blocks_on_bearish_structure():
    cfg = BotConfig()
    snap = evaluate_tape_participation(
        cfg,
        mid=1.05,
        structure=_structure(trend="bearish"),
        ta=_ta(),
    )
    assert snap.active is False


def test_participation_blocks_when_sell_gap_too_wide():
    cfg = BotConfig(alpha_tape_participation_max_sell_gap=1.0)
    snap = evaluate_tape_participation(
        cfg,
        mid=1.05,
        structure=_structure(mean_mid=1.048),
        ta=_ta(buy_score=2.0, sell_score=4.5),
    )
    assert snap.active is False
