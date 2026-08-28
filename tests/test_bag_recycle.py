"""Token-recycle doctrine: dip pullback, last-sell ceiling, powder ceiling, TA waiver."""

from __future__ import annotations

from dataclasses import replace

import pytest

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.decision.harvest_watch import (
    HarvestSessionTracker,
    evaluate_dip_deploy_watch,
    harvest_knobs_from_snapshot,
)
from alpha.decision.reload_regime import deploy_floor_xrp_equiv, powder_ceiling_xrp_equiv
from alpha.decision.price_history import _save_store
from alpha.decision.structure import MarketStructureSnapshot
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.inventory.manager import InventoryManager
from alpha.operator.runtime import validate_override_updates
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


def _inv(*, ratio: float, target: float = 0.85, portfolio: float = 1130.0) -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=ratio,
        target_xrp_ratio=target,
        deviation=ratio - target,
        label="test",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=portfolio,
        xrp_allocation_pct=ratio * 100.0,
        rlusd_allocation_pct=(1.0 - ratio) * 100.0,
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )


def _structure(mid: float) -> MarketStructureSnapshot:
    return MarketStructureSnapshot(
        mid=mid,
        sample_count=20,
        mean_mid=mid,
        recent_high=mid * 1.02,
        recent_low=mid * 0.98,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="neutral",
        swing_high=mid * 1.02,
    )


def _book(mid: float) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=(BookLevel(mid * 0.999, 500.0),),
        asks=(BookLevel(mid * 1.001, 500.0),),
        best_bid=mid * 0.999,
        best_ask=mid * 1.001,
        mid=mid,
        spread=mid * 0.002,
        spread_pct=0.20,
        fetched_utc=utc_now(),
    )


def _risk() -> RiskSnapshot:
    return RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        session_pnl_xrp=0.0,
        preflight_ready=True,
        preflight_summary="ok",
        trading_allowed=True,
        alerts=(),
    )


def _liq(mid: float) -> LiquidityDepth:
    return LiquidityDepth(
        max_slippage_pct=0.5,
        bid_depth_xrp=200.0,
        ask_depth_xrp=200.0,
        best_bid=mid * 0.999,
        best_ask=mid * 1.001,
        mid=mid,
        spread_pct=0.20,
    )


def _ta_bearish(*, buy: float = 1.14, sell: float = 2.0) -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        mid=1.42,
        enabled=True,
        buy_score=buy,
        sell_score=sell,
        breakout_score=0.0,
        bias="bearish",
        entry_buy_allowed=False,
        entry_sell_allowed=True,
        breakout_confirmed=False,
        summary="bearish test",
    )


def _fade_history(tmp_path):
    """24h still green, but ~3% off the local high (live-style fade)."""
    path = tmp_path / "fade.json"
    mids = [1.40] * 2000 + [1.47] * 800 + [1.395] * 200 + [1.427] * 400
    store = {
        "bid": [m * 0.99985 for m in mids],
        "ask": [m * 1.00015 for m in mids],
        "mid": mids,
        "last": [],
    }
    _save_store(store, path)
    return path


def test_dip_arms_on_pullback_from_high_while_24h_green(tmp_path):
    path = _fade_history(tmp_path)
    cfg = BotConfig(
        alpha_accumulation_dip_deploy_enabled=True,
        alpha_accumulation_dip_move_24h_arm_pct=5.0,
        alpha_accumulation_dip_pullback_arm_pct=1.2,
        alpha_accumulation_dip_bounce_arm_pct=0.20,
        alpha_cycle_interval_seconds=15,
    )
    mid = 1.427
    snap = evaluate_dip_deploy_watch(
        cfg,
        inventory=_inv(ratio=0.81),
        mid=mid,
        structure=_structure(mid),
        ta=None,
        rlusd_balance=301.0,
        harvest_phase="idle",
        price_history_path=path,
    )
    assert snap.rolling is not None
    assert snap.rolling.move_pct > 0
    assert snap.rolling.pullback_pct >= 1.2
    assert snap.phase == "armed"
    assert snap.reason == "pullback_from_high"


def test_last_sell_ceiling_blocks_chase():
    cfg = BotConfig(
        alpha_ta_weight=0.0,
        alpha_last_sell_ceiling_enabled=True,
        alpha_min_edge_threshold_pct=0.01,
        min_order_size_xrp=1.0,
        alpha_powder_ceiling_xrp_equiv=0.0,
    )
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    engine.set_harvest(None, None, last_sell_price=1.45)
    mid = 1.46
    decision = engine.evaluate(
        inventory=_inv(ratio=0.81),
        risk=_risk(),
        book=_book(mid),
        liquidity=_liq(mid),
        balances=BalanceSnapshot(xrp=922.0, rlusd=301.0, mid_rlusd_per_xrp=mid, portfolio_xrp_equiv=1133.0),
    )
    assert decision.action == DecisionAction.HOLD
    assert "last_sell_ceiling" in decision.reason


def test_bearish_ta_waived_on_recycle():
    cfg = BotConfig(
        alpha_ta_weight=0.65,
        alpha_dip_waive_bearish_ta=True,
        alpha_last_sell_ceiling_enabled=False,
        alpha_powder_ceiling_xrp_equiv=0.0,
        alpha_min_edge_threshold_pct=0.01,
        min_order_size_xrp=1.0,
        alpha_technical_analysis=replace(
            BotConfig().alpha_technical_analysis, min_buy_score=1.8, enabled=True
        ),
    )
    from alpha.decision.harvest_watch import HarvestWatchSnapshot

    hw = HarvestWatchSnapshot(
        enabled=True,
        phase="idle",
        headline="",
        detail="",
        entry_allowed=False,
        reason="idle",
        pending_reentry=True,
        last_sell_price=1.44,
    )
    knobs = harvest_knobs_from_snapshot(hw, cfg)
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    engine.set_harvest(hw, knobs, reentry_pending=True, last_sell_price=1.44)
    mid = 1.42
    decision = engine.evaluate(
        inventory=_inv(ratio=0.81),
        risk=_risk(),
        book=_book(mid),
        liquidity=_liq(mid),
        balances=BalanceSnapshot(xrp=922.0, rlusd=301.0, mid_rlusd_per_xrp=mid, portfolio_xrp_equiv=1133.0),
        ta=_ta_bearish(),
        structure=_structure(mid),
    )
    assert decision.action == DecisionAction.PLACE_BID
    assert "harvest_reentry" in decision.reason


def test_powder_ceiling_bids_when_under_target():
    cfg = BotConfig(
        alpha_ta_weight=0.0,
        alpha_powder_ceiling_xrp_equiv=90.0,
        alpha_reload_min_rlusd_deploy_xrp_equiv=40.0,
        alpha_last_sell_ceiling_enabled=False,
        alpha_min_edge_threshold_pct=0.01,
        min_order_size_xrp=1.0,
        alpha_weakness_deviation=0.20,
    )
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    mid = 1.42
    decision = engine.evaluate(
        inventory=_inv(ratio=0.81),
        risk=_risk(),
        book=_book(mid),
        liquidity=_liq(mid),
        balances=BalanceSnapshot(xrp=922.0, rlusd=301.0, mid_rlusd_per_xrp=mid, portfolio_xrp_equiv=1133.0),
    )
    assert decision.action == DecisionAction.PLACE_BID
    assert "powder_ceiling" in decision.reason


def test_trim_stop_at_target_blocks_harvest_ask():
    cfg = BotConfig(
        alpha_ta_weight=0.0,
        alpha_trim_stop_at_target=True,
        alpha_strength_deviation=0.05,
        alpha_min_edge_threshold_pct=0.01,
        min_order_size_xrp=1.0,
        alpha_powder_ceiling_xrp_equiv=0.0,
    )
    from alpha.decision.harvest_watch import HarvestWatchSnapshot

    hw = HarvestWatchSnapshot(
        enabled=True,
        phase="armed",
        headline="armed",
        detail="",
        entry_allowed=True,
        reason="armed",
    )
    knobs = harvest_knobs_from_snapshot(hw, cfg)
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    engine.set_harvest(hw, knobs)
    mid = 1.42
    decision = engine.evaluate(
        inventory=_inv(ratio=0.85),
        risk=_risk(),
        book=_book(mid),
        liquidity=_liq(mid),
        balances=BalanceSnapshot(xrp=962.0, rlusd=240.0, mid_rlusd_per_xrp=mid, portfolio_xrp_equiv=1130.0),
    )
    assert decision.action == DecisionAction.HOLD
    assert "harvest_trim" not in (decision.reason or "")


def test_session_preserves_last_sell_across_window_roll(tmp_path):
    sess = HarvestSessionTracker(path=tmp_path / "h.json")
    sess.record_sell_fill(price_rlusd_per_xrp=1.447, size_xrp=39.5)
    sess.set_pending_reentry(enabled=True)
    sess._state["window_start_utc"] = "2020-01-01T00:00:00+00:00"
    sess.tranches_in_window(BotConfig())
    assert sess.last_sell_price() == 1.447
    assert sess.pending_reentry() is True


def test_powder_floor_and_ceiling_scale_with_bag():
    cfg = BotConfig(
        alpha_reload_min_rlusd_deploy_pct=3.5,
        alpha_reload_min_rlusd_deploy_xrp_equiv=40.0,
        alpha_powder_ceiling_pct=8.0,
        alpha_powder_ceiling_xrp_equiv=90.0,
    )
    assert deploy_floor_xrp_equiv(cfg, 1130.0) == pytest.approx(39.55, abs=0.01)
    assert powder_ceiling_xrp_equiv(cfg, 1130.0) == pytest.approx(90.4, abs=0.01)
    assert deploy_floor_xrp_equiv(cfg, 12000.0) == pytest.approx(420.0, abs=0.01)
    assert powder_ceiling_xrp_equiv(cfg, 12000.0) == pytest.approx(960.0, abs=0.01)
    abs_only = BotConfig(
        alpha_reload_min_rlusd_deploy_pct=0.0,
        alpha_reload_min_rlusd_deploy_xrp_equiv=40.0,
        alpha_powder_ceiling_pct=0.0,
        alpha_powder_ceiling_xrp_equiv=90.0,
    )
    assert deploy_floor_xrp_equiv(abs_only, 12000.0) == 40.0
    assert powder_ceiling_xrp_equiv(abs_only, 12000.0) == 90.0


def test_recycle_knobs_are_operator_tunable():
    sanitized, errors = validate_override_updates(
        {
            "alpha_recycle_after_sell_enabled": True,
            "alpha_last_sell_ceiling_enabled": True,
            "alpha_trim_stop_at_target": True,
            "alpha_dip_waive_bearish_ta": True,
            "alpha_drawdown_reload_only_below_floor": True,
            "alpha_accumulation_dip_pullback_arm_pct": 1.2,
            "alpha_powder_ceiling_pct": 8.0,
            "alpha_reload_min_rlusd_deploy_pct": 3.5,
            "alpha_recycle_buy_offset_pct": 0.14,
        }
    )
    assert errors == []
    assert sanitized["alpha_recycle_after_sell_enabled"] is True
    assert sanitized["alpha_powder_ceiling_pct"] == 8.0
    assert sanitized["alpha_reload_min_rlusd_deploy_pct"] == 3.5
