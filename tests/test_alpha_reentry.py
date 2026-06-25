"""Tests for post-exit re-entry gate (Aggressive Bag Growth)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from alpha.decision.reentry import ReentryGate, ReentryExitType
from alpha.decision.structure import MarketStructureSnapshot
from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.types import InventorySnapshot
from config.settings import BotConfig


def _gate(tmp_path: Path, **cfg_overrides: object) -> ReentryGate:
    base = BotConfig(
        alpha_reentry_enabled=True,
        alpha_weakness_deviation=0.02,
        inventory_target_xrp_ratio=0.75,
        alpha_reentry_tp_dip_pct=0.10,
        alpha_reentry_tp_cooldown_cycles=1,
        alpha_reentry_sl_cooldown_cycles=2,
        alpha_reentry_sl_stabilization_pct=0.10,
    )
    for key, value in cfg_overrides.items():
        setattr(base, key, value)
    return ReentryGate(base, persist_path=tmp_path / "reentry.json")


def _weak_inv() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.70,
        target_xrp_ratio=0.75,
        deviation=-0.05,
        label="rlusd_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )


def _ta_allowed() -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        mid=2.0,
        enabled=True,
        buy_score=3.0,
        sell_score=0.5,
        breakout_score=0.0,
        bias="bullish",
        entry_buy_allowed=True,
        entry_sell_allowed=False,
        breakout_confirmed=False,
        summary="test",
    )


def test_tp_exit_blocks_until_dip_and_ta(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    cfg = gate._config
    cfg = replace(cfg, alpha_technical_analysis=replace(cfg.alpha_technical_analysis, enabled=True))
    gate._config = cfg

    gate.record_tp_exit(bracket_id="b1", exit_mid=2.00)
    gate.tick_cycle()

    blocked = gate.blocks_buy(inventory=_weak_inv(), mid=2.01, ta=_ta_allowed())
    assert blocked is not None
    assert "reentry_tp_await_dip" in blocked

    cleared = gate.blocks_buy(inventory=_weak_inv(), mid=1.79, ta=_ta_allowed())
    assert cleared is None


def test_post_tp_cooldown_blocks_before_dip_check(tmp_path: Path) -> None:
    gate = _gate(tmp_path, alpha_reentry_tp_cooldown_cycles=5)
    cfg = gate._config
    cfg = replace(cfg, alpha_technical_analysis=replace(cfg.alpha_technical_analysis, enabled=True))
    gate._config = cfg

    gate.record_tp_exit(bracket_id="b0", exit_mid=2.00)
    # cycles_since_exit=0 — cooldown must block even with dip + strong TA
    blocked = gate.blocks_buy(inventory=_weak_inv(), mid=1.79, ta=_ta_allowed())
    assert blocked is not None
    assert "post_tp_cooldown" in blocked


def test_sl_exit_blocks_until_stabilization(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    cfg = gate._config
    cfg = replace(cfg, alpha_technical_analysis=replace(cfg.alpha_technical_analysis, enabled=True))
    gate._config = cfg

    gate.record_sl_exit(bracket_id="b2", exit_mid=1.90, entry_price=1.95)
    gate.tick_cycle()
    gate.tick_cycle()

    structure_bear = MarketStructureSnapshot(
        mid=1.88,
        sample_count=20,
        mean_mid=1.92,
        recent_high=1.95,
        recent_low=1.85,
        trend="bearish",
        breakout_up=False,
        breakout_down=True,
        summary="bear",
        swing_high=1.95,
    )
    blocked = gate.blocks_buy(
        inventory=_weak_inv(),
        mid=1.88,
        ta=_ta_allowed(),
        structure=structure_bear,
    )
    assert blocked is not None
    assert "reentry_sl_await_stabilization" in blocked

    structure_ok = MarketStructureSnapshot(
        mid=1.87,
        sample_count=20,
        mean_mid=1.90,
        recent_high=1.92,
        recent_low=1.85,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="neutral",
        swing_high=1.92,
    )
    cleared = gate.blocks_buy(
        inventory=_weak_inv(),
        mid=1.87,
        ta=_ta_allowed(),
        structure=structure_ok,
    )
    assert cleared is None


def test_reentry_persists_and_clears(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate.record_tp_exit(bracket_id="b3", exit_mid=2.0)
    assert gate.snapshot.active
    assert gate.snapshot.exit_type == ReentryExitType.TP

    gate.clear(reason="test")
    assert not gate.snapshot.active

    gate2 = ReentryGate(gate._config, persist_path=tmp_path / "reentry.json")
    assert not gate2.snapshot.active


def test_tp_reentry_blocks_low_ta_score(tmp_path: Path) -> None:
    gate = _gate(tmp_path, alpha_reentry_tp_min_ta_score=2.5)
    cfg = gate._config
    cfg = replace(cfg, alpha_technical_analysis=replace(cfg.alpha_technical_analysis, enabled=True))
    gate._config = cfg

    gate.record_tp_exit(bracket_id="b4", exit_mid=2.00)
    gate.tick_cycle()

    weak_ta = TechnicalAnalysisSnapshot(
        mid=1.79,
        enabled=True,
        buy_score=1.0,
        sell_score=0.5,
        breakout_score=0.0,
        bias="neutral",
        entry_buy_allowed=False,
        entry_sell_allowed=False,
        breakout_confirmed=False,
        summary="weak",
    )
    blocked = gate.blocks_buy(inventory=_weak_inv(), mid=1.79, ta=weak_ta)
    assert blocked is not None
    assert "reentry_tp_ta_score" in blocked

    cleared = gate.blocks_buy(
        inventory=_weak_inv(),
        mid=1.79,
        ta=replace(_ta_allowed(), buy_score=2.8),
    )
    assert cleared is None


def test_snapshot_reports_cooldown_remaining(tmp_path: Path) -> None:
    gate = _gate(tmp_path, alpha_reentry_tp_cooldown_cycles=4)
    gate.record_tp_exit(bracket_id="b5", exit_mid=2.0)
    snap = gate.snapshot
    assert snap.in_cooldown is True
    assert snap.cooldown_cycles_remaining == 4


def test_duplicate_tp_exit_does_not_reset_cooldown(tmp_path: Path) -> None:
    gate = _gate(tmp_path, alpha_reentry_tp_cooldown_cycles=4)
    gate.record_tp_exit(bracket_id="b6", exit_mid=2.0)
    gate.tick_cycle()
    gate.tick_cycle()
    assert gate.snapshot.cycles_since_exit == 2

    gate.record_tp_exit(bracket_id="b6", exit_mid=2.0)
    assert gate.snapshot.cycles_since_exit == 2
    assert gate.snapshot.cooldown_cycles_remaining == 2


def test_scratch_sl_uses_short_cooldown(tmp_path: Path) -> None:
    gate = _gate(
        tmp_path,
        alpha_reentry_sl_cooldown_cycles=20,
        alpha_reentry_scratch_sl_cooldown_cycles=2,
        alpha_reentry_scratch_sl_max_loss_pct=0.15,
    )
    gate.record_sl_exit(bracket_id="s1", exit_mid=1.0310, entry_price=1.0310)
    snap = gate.snapshot
    assert snap.sl_tier == "scratch"
    assert snap.cooldown_cycles_required == 2
    assert snap.cooldown_cycles_remaining == 2


def test_sl_cluster_does_not_reset_cooldown(tmp_path: Path) -> None:
    gate = _gate(
        tmp_path,
        alpha_reentry_sl_cooldown_cycles=10,
        alpha_reentry_sl_cluster_window_seconds=3600.0,
    )
    gate.record_sl_exit(bracket_id="c1", exit_mid=1.030, entry_price=1.050)
    gate.tick_cycle()
    gate.tick_cycle()
    assert gate.snapshot.cycles_since_exit == 2

    gate.record_sl_exit(bracket_id="c2", exit_mid=1.029, entry_price=1.048)
    assert gate.snapshot.cycles_since_exit == 2
    assert gate.snapshot.cooldown_cycles_remaining == 8


def test_recovery_early_release_skips_remaining_cooldown(tmp_path: Path) -> None:
    gate = _gate(
        tmp_path,
        alpha_reentry_sl_cooldown_cycles=10,
        alpha_reentry_recovery_enabled=True,
        alpha_reentry_recovery_release_pct=0.05,
        alpha_reentry_recovery_min_cycles=2,
    )
    cfg = gate._config
    cfg = replace(cfg, alpha_technical_analysis=replace(cfg.alpha_technical_analysis, enabled=True))
    gate._config = cfg

    gate.record_sl_exit(bracket_id="r1", exit_mid=1.000, entry_price=1.020)
    gate.tick_cycle()
    gate.tick_cycle()

    structure_ok = MarketStructureSnapshot(
        mid=1.002,
        sample_count=20,
        mean_mid=1.01,
        recent_high=1.02,
        recent_low=0.99,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="ok",
        swing_high=1.02,
    )
    blocked = gate.blocks_buy(
        inventory=_weak_inv(),
        mid=1.002,
        ta=_ta_allowed(),
        structure=structure_ok,
    )
    assert blocked is None or "post_sl_cooldown" not in blocked
    assert gate.snapshot.cycles_since_exit >= 10


def test_post_clear_buy_spacing_blocks_rapid_bids(tmp_path: Path) -> None:
    gate = _gate(tmp_path, alpha_reentry_post_clear_buy_spacing_cycles=3)
    gate.record_tp_exit(bracket_id="sp1", exit_mid=2.0)
    gate.clear(reason="buy_executed")

    blocked = gate.blocks_buy(inventory=_weak_inv(), mid=1.79, ta=_ta_allowed())
    assert blocked is not None
    assert "reentry_reload_spacing" in blocked

    gate.tick_cycle()
    gate.tick_cycle()
    gate.tick_cycle()
    cleared = gate.blocks_buy(inventory=_weak_inv(), mid=1.79, ta=_ta_allowed())
    assert cleared is None
