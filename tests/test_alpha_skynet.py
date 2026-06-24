"""Tests for Alpha SKYNET Grok advisor."""

from __future__ import annotations

import json

import pytest

from alpha.hud.skynet import (
    _SYSTEM_PROMPT,
    build_skynet_context,
    filter_applicable_suggestions,
    parse_grok_advisor_response,
)
from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS
from config.settings import BotConfig


def test_system_prompt_format_escapes_json_braces():
    allowed = ", ".join(sorted(OPERATOR_TUNABLE_KEYS)[:5])
    rendered = _SYSTEM_PROMPT.format(allowed_keys=allowed)
    assert allowed in rendered
    assert '"reasoning"' in rendered
    assert "{allowed_keys}" not in rendered


def test_parse_grok_advisor_response_json():
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
    parsed = parse_grok_advisor_response(raw)
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
    parsed = parse_grok_advisor_response(raw)
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


def test_build_skynet_context_includes_decision():
    ctx = build_skynet_context(
        {
            "network": "mainnet",
            "dry_run": False,
            "inventory": {"deviation": -0.2, "label": "heavy_rlusd"},
            "decision": {"action": "hold", "reason": "max_pending_buys=5"},
            "recent_activity": [],
        },
        operator_config={"alpha_max_pending_buys": 5},
    )
    assert "max_pending_buys=5" in ctx
    assert "heavy_rlusd" in ctx
    assert "Scenario playbook" in ctx
    assert "likely_scenarios=" in ctx


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
