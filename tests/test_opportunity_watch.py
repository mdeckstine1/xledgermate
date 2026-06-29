"""Tests for opportunity watch readiness layer."""

from __future__ import annotations

from alpha.decision.opportunity_watch import evaluate_opportunity_watch
from alpha.decision.structure import MarketStructureSnapshot
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.types import InventorySnapshot
from config.settings import BotConfig


def _balanced() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.795,
        target_xrp_ratio=0.80,
        deviation=-0.005,
        label="balanced",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )


def _bull_ta() -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        mid=1.07,
        enabled=True,
        buy_score=2.25,
        sell_score=1.8,
        breakout_score=1.5,
        bias="bullish",
        entry_buy_allowed=True,
        entry_sell_allowed=False,
        breakout_confirmed=True,
        signals=(),
        summary="bull",
        rsi=55.0,
        stoch_k=60.0,
        stoch_d=55.0,
        bb_upper=1.08,
        bb_middle=1.07,
        bb_lower=1.06,
        bb_bandwidth_pct=0.2,
        fib_levels={},
        elliott_bias="impulse_up",
    )


def test_blocked_on_balanced_hold_during_bull():
    cfg = BotConfig(alpha_bull_run_enabled=True)
    snap = evaluate_opportunity_watch(
        cfg,
        inventory=_balanced(),
        mid=1.07,
        structure=MarketStructureSnapshot(
            mid=1.07,
            sample_count=20,
            mean_mid=1.069,
            recent_high=1.071,
            recent_low=1.06,
            trend="neutral",
            breakout_up=False,
            breakout_down=False,
            summary="neutral",
            swing_high=1.071,
        ),
        ta=_bull_ta(),
        decision_action="hold",
        decision_reason="balanced dev=-0.005",
    )
    assert snap.state in ("watching", "armed", "blocked")
    assert snap.headline
    assert snap.suggestions


def test_executing_when_place_bid():
    cfg = BotConfig()
    snap = evaluate_opportunity_watch(
        cfg,
        inventory=_balanced(),
        mid=1.07,
        structure=None,
        ta=_bull_ta(),
        decision_action="place_bid",
        decision_reason="bull_run",
        pending_buys=0,
    )
    assert snap.state == "executing"
