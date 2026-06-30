"""Tests for Alpha SKYNET advisor."""

from __future__ import annotations

import json

import pytest

from alpha.hud.skynet import (
    _SYSTEM_PROMPT,
    build_skynet_context,
    filter_applicable_suggestions,
    parse_skynet_advisor_response,
)
from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS
from config.settings import BotConfig


def test_system_prompt_format_escapes_json_braces():
    allowed = ", ".join(sorted(OPERATOR_TUNABLE_KEYS)[:5])
    rendered = _SYSTEM_PROMPT.format(allowed_keys=allowed)
    assert allowed in rendered
    assert '"reasoning"' in rendered
    assert "{allowed_keys}" not in rendered


def test_parse_skynet_advisor_response_json():
    raw = json.dumps(
        {
            "reasoning": "Inventory is RLUSD heavy.",
            "summary": "Wait for dip",
            "suggested_changes": [
                {
                    "key": "alpha_buy_limit_offset_pct",
                    "value": 0.2,
                    "reason": "more edge",
                }
            ],
            "warnings": ["mainnet"],
        }
    )
    parsed = parse_skynet_advisor_response(raw)
    assert parsed["summary"] == "Wait for dip"
    assert len(parsed["suggested_changes"]) == 1
    assert parsed["suggested_changes"][0]["key"] == "alpha_buy_limit_offset_pct"


def test_parse_target_xrp_pct_alias():
    raw = json.dumps(
        {
            "reasoning": "x",
            "summary": "y",
            "suggested_changes": [
                {"key": "target_xrp_pct", "value": 75, "reason": "grow bag"},
            ],
        }
    )
    parsed = parse_skynet_advisor_response(raw)
    assert parsed["suggested_changes"][0]["key"] == "inventory_target_xrp_ratio"
    assert parsed["suggested_changes"][0]["value"] == pytest.approx(0.75)


def test_filter_blocks_dry_run():
    base = BotConfig()
    sanitized, accepted, errors = filter_applicable_suggestions(
        [{"key": "dry_run", "value": True, "reason": "test"}],
        base=base,
    )
    assert not sanitized
    assert any("dry_run" in e for e in errors)


def test_filter_accepts_valid_knob():
    base = BotConfig()
    sanitized, accepted, errors = filter_applicable_suggestions(
        [{"key": "alpha_max_pending_buys", "value": 3, "reason": "ladder"}],
        base=base,
    )
    assert not errors
    assert sanitized.get("alpha_max_pending_buys") == 3
    assert len(accepted) == 1


def test_filter_accepts_hud_alias_keys():
    base = BotConfig()
    sanitized, accepted, errors = filter_applicable_suggestions(
        [
            {"key": "risk_per_trade_pct", "value": 2.5, "reason": "size"},
            {"key": "sl_cooldown_cycles", "value": 20, "reason": "defense"},
        ],
        base=base,
    )
    assert not errors
    assert sanitized["alpha_risk_per_trade_pct"] == 2.5
    assert sanitized["alpha_reentry_sl_cooldown_cycles"] == 20
    assert accepted[0]["key"] == "alpha_risk_per_trade_pct"


def test_filter_accepts_accumulation_dev_knobs():
    base = BotConfig()
    sanitized, accepted, errors = filter_applicable_suggestions(
        [
            {"key": "alpha_accumulation_max_deviation", "value": 0.08, "reason": "scale rip"},
            {"key": "alpha_bull_run_max_deviation", "value": 0.08, "reason": "momentum path"},
        ],
        base=base,
    )
    assert not errors
    assert sanitized["alpha_accumulation_max_deviation"] == 0.08
    assert sanitized["alpha_bull_run_max_deviation"] == 0.08


def test_build_skynet_context_includes_gate_diagnostics_and_structure():
    ctx = build_skynet_context(
        {
            "network": "mainnet",
            "mid": 3.52,
            "engine_cycle": 42,
            "inventory": {"deviation": 0.075, "label": "balanced"},
            "decision": {"action": "hold", "reason": "balanced dev=+0.075"},
            "structure": {
                "trend": "neutral",
                "breakout_up": False,
                "mean_mid": 3.50,
                "recent_high": 3.55,
                "recent_low": 3.40,
            },
            "technical_analysis": {
                "enabled": True,
                "bias": "bullish",
                "buy_score": 3.52,
                "breakout_score": 0.5,
                "breakout_confirmed": False,
                "entry_buy_allowed": True,
            },
            "momentum_entry": {"active": False, "reason": "dev=+0.075>bull_max=+0.040"},
            "tape_participation": {"active": False, "reason": "ta_bias=bullish"},
            "accumulation_regime": {"phase": "primed", "armed": False, "blockers": []},
            "brackets": {"records": []},
            "risk": {},
            "recent_activity": [],
        },
        effective_config=BotConfig(),
    )
    assert "Engine gate diagnostics" in ctx
    assert "accumulation_dev_cap" in ctx
    assert "Market structure" in ctx
    assert "breakout_up=False" in ctx
    assert "breakout_confirmed" in ctx
    assert "engine_cycle=42" in ctx


def test_build_skynet_context_includes_decision():
    ctx = build_skynet_context(
        {
            "network": "mainnet",
            "dry_run": False,
            "inventory": {"deviation": -0.2, "label": "heavy_rlusd"},
            "decision": {"action": "hold", "reason": "max_pending_buys=5"},
            "recent_activity": [],
        },
        operator_config={"alpha_max_pending_buys": 5, "alpha_operator_phase": "trust"},
    )
    assert "max_pending_buys=5" in ctx
    assert "heavy_rlusd" in ctx
    assert "Scenario playbook" in ctx
    assert "likely_scenarios=" in ctx
    assert "phase=trust" in ctx
    assert "Operator knob allowlist" in ctx
    assert "Operator phase scenarios (S–U)" in ctx


def test_build_skynet_user_message_settings_intent():
    from alpha.hud.skynet_scenarios import build_skynet_user_message

    msg = build_skynet_user_message(
        user_prompt="Set risk to 4% and stickier bids",
        context="=== snapshot ===",
    )
    assert "OPERATOR PROMPT (PRIMARY" in msg
    assert "suggested_changes" in msg
    assert "Set risk to 4%" in msg
    assert msg.index("Set risk to 4%") < msg.index("=== snapshot ===")


def test_build_skynet_user_message_bullish_buy_intent():
    from alpha.hud.skynet_scenarios import build_skynet_user_message, classify_prompt_intent

    prompt = (
        "looks like we are in a long consolidation phase after a drop, "
        "lets consider moving to a strong buy now we are in bullish signals"
    )
    tags = classify_prompt_intent(prompt)["tags"]
    assert "bullish_buy" in tags
    assert "consolidation" in tags

    msg = build_skynet_user_message(user_prompt=prompt, context="=== snapshot ===")
    assert "BULLISH / BUY intent detected" in msg
    assert "Do NOT tighten alpha_stale_pending_buy_max_drift_pct" in msg
    assert prompt in msg
    assert msg.index(prompt) < msg.index("=== snapshot ===")


def test_infer_scenario_hints_accumulation_regime_kwarg():
    from alpha.hud.skynet_scenarios import infer_scenario_hints

    hints = infer_scenario_hints(
        decision_reason="balanced dev=+0.02",
        inventory={"deviation": 0.02, "label": "balanced"},
        accumulation_regime={"armed": True, "phase": "armed"},
        reload_regime={"blocks_accumulation": True, "phase": "watching"},
        opportunity_watch={"state": "armed"},
    )
    assert "V" in hints
    assert "W" in hints
    assert "U" in hints


def test_build_skynet_context_with_accumulation_reload():
    ctx = build_skynet_context(
        {
            "network": "mainnet",
            "dry_run": False,
            "mid": 1.1,
            "inventory": {"deviation": 0.02, "label": "balanced"},
            "decision": {"action": "hold", "reason": "balanced dev=+0.02"},
            "accumulation_regime": {"phase": "armed", "armed": True},
            "reload_regime": {"phase": "watching", "blocks_accumulation": True},
            "opportunity_watch": {"state": "armed"},
            "brackets": {"records": []},
            "risk": {},
            "recent_activity": [],
        },
        operator_config={"alpha_operator_phase": "trust"},
    )
    assert "accumulation_regime" in ctx.lower() or "Accumulation" in ctx
    assert "likely_scenarios=" in ctx


def test_infer_scenario_hints_max_pending_rlusd_heavy():
    from alpha.hud.skynet_scenarios import infer_scenario_hints

    hints = infer_scenario_hints(
        decision_reason="max_pending_buys=3",
        inventory={"deviation": -0.27, "label": "heavy_rlusd"},
        stale_snapshot={"over_cap_count": 0},
    )
    assert "C" not in hints
    assert "I" in hints


def test_infer_scenario_hints_post_sl():
    from alpha.hud.skynet_scenarios import infer_scenario_hints

    hints = infer_scenario_hints(decision_reason="post_sl_cooldown cycles=1/8")
    assert "K" in hints


def test_operator_phase_normalize_and_snapshot():
    from alpha.hud.operator_phase import (
        DEFAULT_OPERATOR_PHASE,
        build_operator_phase_context_block,
        normalize_operator_phase,
        phase_snapshot_fields,
    )
    from alpha.operator.runtime import effective_config_snapshot, validate_override_updates

    assert normalize_operator_phase("TRUST") == "trust"
    assert normalize_operator_phase("eager") == "aggressive"
    assert normalize_operator_phase("bogus") == DEFAULT_OPERATOR_PHASE
    assert phase_snapshot_fields({})["alpha_operator_phase"] == "trust"
    assert phase_snapshot_fields({"alpha_operator_phase": "scale"})["alpha_operator_phase_label"] == "Scale"
    block = build_operator_phase_context_block("trust")
    assert "phase=trust" in block
    assert "session_pnl_xrp" in block or "MTM" in block or "realized" in block.lower()

    sanitized, errors = validate_override_updates({"alpha_operator_phase": "scale"})
    assert not errors
    assert sanitized["alpha_operator_phase"] == "scale"

    snap = effective_config_snapshot(BotConfig(), {"alpha_operator_phase": "aggressive"})
    assert snap["alpha_operator_phase"] == "aggressive"


def test_build_skynet_user_message_includes_operator_phase():
    from alpha.hud.skynet_scenarios import build_skynet_user_message

    msg = build_skynet_user_message(
        user_prompt="summarize",
        context="=== snapshot ===",
        operator_phase="trust",
    )
    assert "OPERATOR PHASE active: trust" in msg
    assert "lowering alpha_buy_limit_offset_pct below" in msg


def test_market_regime_normalize_and_snapshot():
    from alpha.hud.operator_market_regime import (
        DEFAULT_MARKET_REGIME,
        build_market_regime_context_block,
        market_regime_snapshot_fields,
        normalize_market_regime,
    )
    from alpha.operator.runtime import validate_override_updates

    assert normalize_market_regime("BEAR") == "bear"
    assert normalize_market_regime("chop") == "neutral"
    assert normalize_market_regime("bogus") == DEFAULT_MARKET_REGIME
    assert market_regime_snapshot_fields({})["alpha_operator_market_regime"] == "neutral"
    assert market_regime_snapshot_fields({"alpha_operator_market_regime": "bear"})[
        "alpha_operator_market_regime_label"
    ] == "Bear"
    block = build_market_regime_context_block("bear")
    assert "market_regime=bear" in block
    sanitized, errors = validate_override_updates({"alpha_operator_market_regime": "neutral"})
    assert not errors
    assert sanitized["alpha_operator_market_regime"] == "neutral"
    sanitized2, _ = validate_override_updates({"alpha_operator_market_regime": "moon"})
    assert sanitized2["alpha_operator_market_regime"] == "neutral"


def test_build_skynet_user_message_includes_market_regime():
    from alpha.hud.skynet_scenarios import build_skynet_user_message

    msg = build_skynet_user_message(
        user_prompt="defensive",
        context="=== snapshot ===",
        market_regime="bear",
    )
    assert "MARKET REGIME active: bear" in msg
    assert "Capital preservation first" in msg
