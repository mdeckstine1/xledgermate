"""Tests for Unassed (unbrick bag-growth) preset."""

from __future__ import annotations

from alpha.hud.unassed_preset import (
    UNASSED_OPERATOR_OVERRIDES,
    compare_unassed_to_stack_growth,
    unassed_preset_payload,
)


def test_unassed_preset_unbricks_key_knobs() -> None:
    payload = unassed_preset_payload()
    ov = payload["operator_overrides"]
    assert ov["alpha_operator_phase"] == "scale"
    assert ov["alpha_strength_deviation"] == 0.06
    assert ov["alpha_bull_run_max_deviation"] == 0.15
    assert ov["alpha_accumulation_max_deviation"] == 0.15
    assert ov["alpha_ta_min_sell_score"] == 2.0
    assert ov["alpha_reload_min_rlusd_deploy_xrp_equiv"] == 18.0
    assert ov["alpha_reload_block_accumulation_until_funded"] is False
    assert ov["bracket_trailing_enabled"] is False
    assert ov["initial_stop_loss_pct"] == 0.09
    assert ov["take_profit_rr"] == 0.0
    assert ov["take_profit_pct"] == 0.025
    assert "Unassed" in payload["label"] or "unbrick" in payload["description"].lower()


def test_unassed_vs_stack_growth() -> None:
    cmp = compare_unassed_to_stack_growth()
    diff = cmp["different_operator_keys"]
    assert diff["alpha_strength_deviation"]["stack_growth"] == 0.14
    assert diff["alpha_strength_deviation"]["unassed"] == 0.06
    assert UNASSED_OPERATOR_OVERRIDES["alpha_reload_min_rlusd_deploy_xrp_equiv"] == 18.0
