"""Tests for long-build preset."""

from __future__ import annotations

from alpha.hud.long_build_preset import (
    LONG_BUILD_OPERATOR_OVERRIDES,
    compare_long_build_to_walkaway,
    long_build_preset_payload,
)
from alpha.hud.walkaway_preset import WALKAWAY_OPERATOR_OVERRIDES


def test_long_build_preset_scale_and_wider_brackets() -> None:
    payload = long_build_preset_payload()
    ov = payload["operator_overrides"]
    assert ov["alpha_operator_phase"] == "scale"
    assert ov["alpha_operator_market_regime"] == "bull"
    assert ov["inventory_target_xrp_ratio"] == 0.80
    assert ov["alpha_risk_per_trade_pct"] == 3.0
    assert ov["initial_stop_loss_pct"] == 0.03
    assert ov["take_profit_rr"] == 2.0
    assert ov["alpha_stale_pending_buy_max_drift_pct"] == 0.40
    assert ov["alpha_max_pending_buys"] == 1
    assert payload["agent_patch"]["interval_cycles_min"] == 8


def test_long_build_vs_walkaway_comparison() -> None:
    cmp = compare_long_build_to_walkaway()
    assert cmp["summary"]
    diff = cmp["different_operator_keys"]
    assert diff["alpha_operator_phase"]["walkaway"] == "trust"
    assert diff["alpha_operator_phase"]["long_build"] == "scale"
    assert diff["alpha_risk_per_trade_pct"]["walkaway"] == 2.0
    assert diff["alpha_risk_per_trade_pct"]["long_build"] == 3.0
    assert "inventory_target_xrp_ratio" in cmp["long_build_only_operator_keys"]
    assert "initial_stop_loss_pct" in cmp["long_build_only_operator_keys"]
    # Walk-away does not set brackets — long build adds swing horizon knobs.
    assert "alpha_reentry_tp_cooldown_cycles" in WALKAWAY_OPERATOR_OVERRIDES
    assert WALKAWAY_OPERATOR_OVERRIDES["alpha_reentry_tp_cooldown_cycles"] == 12
    assert LONG_BUILD_OPERATOR_OVERRIDES["alpha_reentry_tp_cooldown_cycles"] == 18
