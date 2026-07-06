"""Tests for stack-growth preset."""

from __future__ import annotations

from alpha.hud.stack_growth_preset import (
    STACK_GROWTH_OPERATOR_OVERRIDES,
    compare_stack_growth_to_long_build,
    stack_growth_preset_payload,
)


def test_stack_growth_preset_targets_coin_count() -> None:
    payload = stack_growth_preset_payload()
    ov = payload["operator_overrides"]
    assert ov["alpha_operator_phase"] == "scale"
    assert ov["inventory_target_xrp_ratio"] == 0.88
    assert ov["alpha_strength_deviation"] == 0.11
    assert ov["alpha_weakness_deviation"] == 0.04
    assert ov["alpha_ta_min_sell_score"] == 4.0
    assert ov["alpha_max_pending_sells"] == 1
    assert ov["alpha_max_pending_buys"] == 2


def test_stack_growth_vs_long_build() -> None:
    cmp = compare_stack_growth_to_long_build()
    diff = cmp["different_operator_keys"]
    assert diff["inventory_target_xrp_ratio"]["stack_growth"] == 0.88
    assert diff["inventory_target_xrp_ratio"]["long_build"] == 0.80
    assert diff["alpha_strength_deviation"]["stack_growth"] == 0.11
    assert STACK_GROWTH_OPERATOR_OVERRIDES["alpha_ta_min_sell_score"] == 4.0
