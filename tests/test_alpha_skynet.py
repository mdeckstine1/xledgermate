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
