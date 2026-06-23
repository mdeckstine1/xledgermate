"""Tests for Alpha SKYNET Phase 2 bounded agent."""

from __future__ import annotations

from pathlib import Path

from alpha.hud.skynet_agent import (
    _AGENT_SYSTEM_PROMPT,
    _DEFAULT_GUARDRAILS,
    default_agent_config,
    describe_knob_change,
    filter_guardrailed_suggestions,
    load_agent_config,
    merge_agent_patch,
    should_run_agent,
)
from config.settings import BotConfig


def test_agent_system_prompt_format_escapes_json():
    rendered = _AGENT_SYSTEM_PROMPT.format(
        allowed_keys="k1, k2",
        guardrail_lines="- alpha_risk_per_trade_pct: min=0.1 max=2",
        max_changes=2,
    )
    assert '"reasoning"' in rendered
    assert "k1, k2" in rendered


def test_describe_knob_change_target_pct():
    desc = describe_knob_change("inventory_target_xrp_ratio", 0.65, 0.72)
    assert "target_xrp_pct" in desc
    assert "65" in desc
    assert "72" in desc
    assert desc.startswith("raise")


def test_filter_guardrailed_rejects_out_of_range(tmp_path: Path):
    base = BotConfig()
    guardrails = dict(_DEFAULT_GUARDRAILS)
    guardrails["alpha_risk_per_trade_pct"] = {"min": 0.2, "max": 1.0}
    guardrails["max_changes_per_cycle"] = 2

    safe, rejected, errors = filter_guardrailed_suggestions(
        [
            {"key": "alpha_risk_per_trade_pct", "value": 3.0, "reason": "too high"},
            {"key": "alpha_max_pending_buys", "value": 3, "reason": "ok"},
        ],
        guardrails=guardrails,
        base=base,
        current_effective={"alpha_risk_per_trade_pct": 0.5, "alpha_max_pending_buys": 5},
    )
    assert not any(c["key"] == "alpha_risk_per_trade_pct" for c in safe)
    assert any(c["key"] == "alpha_risk_per_trade_pct" for c in rejected)
    assert any(c["key"] == "alpha_max_pending_buys" for c in safe)
    assert errors


def test_filter_guardrailed_max_changes(tmp_path: Path):
    base = BotConfig()
    guardrails = dict(_DEFAULT_GUARDRAILS)
    guardrails["max_changes_per_cycle"] = 1

    safe, rejected, _ = filter_guardrailed_suggestions(
        [
            {"key": "alpha_max_pending_buys", "value": 2, "reason": "a"},
            {"key": "alpha_ta_weight", "value": 0.8, "reason": "b"},
        ],
        guardrails=guardrails,
        base=base,
        current_effective={"alpha_max_pending_buys": 5, "alpha_ta_weight": 1.0},
    )
    assert len(safe) == 1
    assert len(rejected) == 1


def test_should_run_agent_cycle_gate():
    agent = default_agent_config()
    agent["agent_enabled"] = True
    agent["next_run_engine_cycle"] = 10
    assert not should_run_agent(agent, 9)
    assert should_run_agent(agent, 10)


def test_merge_agent_patch_persists(tmp_path: Path):
    path = tmp_path / "agent.json"
    cfg, errors = merge_agent_patch(
        {
            "agent_enabled": True,
            "interval_cycles_min": 4,
            "interval_cycles_max": 6,
            "guardrails": {"max_changes_per_cycle": 3},
        },
        path=path,
    )
    assert not errors
    assert cfg["agent_enabled"] is True
    loaded = load_agent_config(path)
    assert loaded["interval_cycles_min"] == 4
    assert loaded["guardrails"]["max_changes_per_cycle"] == 3


def test_merge_agent_patch_rejects_bad_interval(tmp_path: Path):
    _, errors = merge_agent_patch(
        {"interval_cycles_min": 10, "interval_cycles_max": 2},
        path=tmp_path / "agent.json",
    )
    assert errors
