"""Tests for production HUD intel + competitor helpers."""

from __future__ import annotations

from experimental.ws_feed.hud_intel_support import (
    our_lane_xrp_from_runtime,
    resolve_hud_intel_fields,
)


def test_resolve_hud_intel_user_key_wins() -> None:
    fields = resolve_hud_intel_fields(
        {
            "intel_ai_provider": "grok",
            "intel_ai_key": "xai-user-key",
            "intel_ai_model": "grok-3-mini",
            "intel_ai_enabled": True,
        }
    )
    assert fields["intel_ai_key"] == "xai-user-key"
    assert fields["intel_ai_model"] == "grok-3-mini"
    assert fields["intel_ai_enabled"] is True
    assert fields["intel_ai_provider"] == "grok"


def test_resolve_hud_intel_key_forces_grok_provider(tmp_path, monkeypatch) -> None:
    from experimental.ws_feed import hud_intel_support as mod

    path = tmp_path / "logs" / "hud_intel_config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"intel_ai_provider":"stub","intel_ai_key":"xai-persisted","intel_ai_model":"grok-3","intel_ai_enabled":true}',
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "INTEL_CONFIG_PATH", path)
    fields = resolve_hud_intel_fields({})
    assert fields["intel_ai_key"] == "xai-persisted"
    assert fields["intel_ai_provider"] == "grok"
    assert fields["intel_ai_enabled"] is True


def test_our_lane_from_quote_intents() -> None:
    rt = {
        "quote_intents": [
            {"level": 1, "side": "bid", "price": 1.2, "size_xrp": 7.5},
            {"level": 1, "side": "ask", "price": 1.21, "size_xrp": 7.5},
        ]
    }
    assert our_lane_xrp_from_runtime(rt, fallback_l1=15.0) == 7.5
