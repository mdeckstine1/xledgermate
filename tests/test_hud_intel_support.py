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


def test_lane_ladder_hud_fields_l2_l3() -> None:
    from experimental.ws_feed.hud_intel_support import lane_ladder_hud_fields, lane_touch_xrp_from_intents

    intents = [
        {"level": 1, "side": "bid", "size_xrp": 10.0},
        {"level": 1, "side": "ask", "size_xrp": 9.0},
        {"level": 2, "side": "bid", "size_xrp": 6.0, "planned": True},
        {"level": 2, "side": "ask", "size_xrp": 5.4, "planned": True},
        {"level": 3, "side": "bid", "size_xrp": 3.0, "planned": True},
        {"level": 3, "side": "ask", "size_xrp": 2.7, "planned": True},
    ]
    assert lane_touch_xrp_from_intents(intents, 2) == 6.0
    assert lane_touch_xrp_from_intents(intents, 3) == 3.0
    fields = lane_ladder_hud_fields({"quote_intents": intents})
    assert fields["our_lane_l2_xrp"] == 6.0
    assert fields["our_lane_l3_xrp"] == 3.0


def test_planned_lane_touch_from_l1_only() -> None:
    from experimental.ws_feed.hud_intel_support import lane_ladder_hud_fields, planned_lane_touch_xrp

    rt = {"our_lane_xrp": 10.0, "quote_intents": [
        {"level": 1, "side": "bid", "size_xrp": 10.0},
        {"level": 1, "side": "ask", "size_xrp": 9.5},
    ]}
    assert planned_lane_touch_xrp(rt, 2) == 6.0
    assert planned_lane_touch_xrp(rt, 3) == 3.0
    fields = lane_ladder_hud_fields(rt)
    assert fields["our_lane_l2_xrp"] == 6.0
    assert fields["our_lane_l3_xrp"] == 3.0


def test_find_competitor_profile_peer_first() -> None:
    from experimental.ws_feed.hud_intel_support import build_competitor_analysis_context, find_competitor_profile

    state = {
        "our_lane_xrp": 11.0,
        "peer_lane_low_xrp": 4.4,
        "peer_lane_high_xrp": 27.5,
        "top_peers": [
            {
                "account": "rPeerAddr123...",
                "account_full": "rPeerAddr123456789012345678901234",
                "touch_xrp": 10.5,
                "last_spread": 0.08,
                "avg_spread": 0.09,
                "activity": 42,
                "cancels": 3,
                "sides": "b5/a5",
            }
        ],
        "top_competitors": [
            {
                "account": "rWhale999...",
                "account_full": "rWhale999000000000000000000000000",
                "touch_xrp": 300000.0,
                "last_spread": 0.07,
                "avg_spread": 0.08,
                "activity": 99,
                "cancels": 1,
                "sides": "b2/a2",
            }
        ],
    }
    prof, src = find_competitor_profile(state, "rPeerAddr123456789012345678901234")
    assert src == "peer_lane"
    assert prof is not None
    assert prof["touch_xrp"] == 10.5

    briefing = build_competitor_analysis_context(state, "rPeerAddr123456789012345678901234")
    assert briefing["in_peer_lane"] is True
    assert "IN peer touch band" in briefing["lane_note"]
    assert "touch_xrp=10.50" in briefing["prompt_block"]

    whale = build_competitor_analysis_context(state, "rWhale999000000000000000000000000")
    assert whale["in_peer_lane"] is False
    assert "OUT of peer touch band" in whale["lane_note"]
    assert "Scrape evidence" in whale["evidence_header"]
