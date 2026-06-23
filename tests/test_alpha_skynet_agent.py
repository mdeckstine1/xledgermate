"""Tests for Alpha SKYNET Phase 2 bounded agent and Phase 3 full mode."""

from __future__ import annotations

from pathlib import Path

from alpha.hud.skynet_agent import (
    _AGENT_SYSTEM_PROMPT,
    _DEFAULT_GUARDRAILS,
    _FULL_MODE_CONFIRM,
    _FULL_MODE_SYSTEM_PROMPT,
    append_audit_entry,
    default_agent_config,
    describe_knob_change,
    detect_significant_events,
    evaluate_emergency_rules,
    filter_guardrailed_suggestions,
    load_agent_config,
    load_audit_entries,
    merge_agent_patch,
    pause_full_skynet_mode,
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


def test_full_mode_system_prompt_format():
    rendered = _FULL_MODE_SYSTEM_PROMPT.format(
        allowed_keys="k1",
        guardrail_lines="- alpha_risk_per_trade_pct: min=0.1 max=2",
        max_changes=3,
    )
    assert "disciplined" in rendered.lower()
    assert '"reasoning"' in rendered


def test_merge_full_mode_requires_confirm(tmp_path: Path):
    path = tmp_path / "agent.json"
    _, errors = merge_agent_patch(
        {"agent_enabled": True, "full_mode_enabled": True},
        path=path,
    )
    assert errors
    assert any(_FULL_MODE_CONFIRM in e for e in errors)

    cfg, errors = merge_agent_patch(
        {
            "agent_enabled": True,
            "full_mode_enabled": True,
            "confirm": _FULL_MODE_CONFIRM,
        },
        path=path,
    )
    assert not errors
    assert cfg["full_mode_enabled"] is True


def test_emergency_drawdown_pauses_trading(tmp_path: Path):
    from alpha.operator.runtime import OperatorRuntimeStore

    overrides_path = tmp_path / "overrides.json"
    runtime = OperatorRuntimeStore(
        overrides_path=overrides_path,
        commands_path=tmp_path / "commands.json",
    )
    hud = {
        "risk": {"drawdown_pct": 9.5, "session_pnl_xrp": 0.0},
        "trading_enabled": True,
    }
    action = evaluate_emergency_rules(
        hud,
        emergency_rules={"enabled": True, "drawdown_pause_pct": 8.0, "session_loss_pause_xrp": 25.0},
        runtime=runtime,
        trading_enabled=True,
    )
    assert action is not None
    assert action["applied"] is True
    assert runtime.load_overrides().get("trading_enabled") is False


def test_detect_significant_events():
    hud = {
        "engine_cycle": 10,
        "decision": {"action": "hold"},
        "risk": {"kill_switch_active": False, "drawdown_pct": 2.0, "session_pnl_xrp": 0.0},
        "inventory": {"deviation": -0.4},
        "trading_enabled": True,
    }
    last = {
        "decision_action": "place_bid",
        "kill_switch_active": False,
        "drawdown_pct": 0.5,
        "session_pnl_xrp": 10.0,
        "inventory_deviation": -0.3,
    }
    triggered, reasons = detect_significant_events(hud, last)
    assert triggered
    assert any("decision_changed" in r for r in reasons)


def test_audit_log_roundtrip(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    append_audit_entry({"event": "test", "summary": "hello"}, path=path)
    entries = load_audit_entries(limit=5, path=path)
    assert len(entries) == 1
    assert entries[0]["summary"] == "hello"


def test_pause_full_skynet_mode(tmp_path: Path, monkeypatch):
    path = tmp_path / "agent.json"
    merge_agent_patch(
        {"agent_enabled": True, "full_mode_enabled": True, "confirm": _FULL_MODE_CONFIRM},
        path=path,
    )
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr("alpha.hud.skynet_agent._DEFAULT_AGENT_PATH", path)
    monkeypatch.setattr("alpha.hud.skynet_agent._AUDIT_PATH", audit)
    cfg = pause_full_skynet_mode(path=path, audit_path=audit)
    assert cfg["full_mode_enabled"] is False
    assert load_audit_entries(path=audit)[0]["event"] == "full_mode_paused"


def test_should_run_on_significant_event():
    agent = default_agent_config()
    agent["agent_enabled"] = True
    agent["next_run_engine_cycle"] = 100
    hud = {
        "engine_cycle": 5,
        "decision": {"action": "hold"},
        "risk": {"kill_switch_active": True, "drawdown_pct": 1.0, "session_pnl_xrp": 0.0},
        "inventory": {"deviation": 0.0},
    }
    last = {
        "kill_switch_active": False,
        "decision_action": "place_bid",
        "drawdown_pct": 0.0,
        "session_pnl_xrp": 0.0,
        "inventory_deviation": 0.0,
    }
    agent["last_event_snapshot"] = last
    assert should_run_agent(agent, 5, hud)
