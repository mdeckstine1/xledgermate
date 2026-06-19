"""Shadow E3 peer-lane calibration (HUD-only)."""

from __future__ import annotations

from experimental.ws_feed.hud_intel_support import (
    SHADOW_E3_PORTFOLIO_XRP_EQUIV,
    build_competitor_analysis_context,
    compute_shadow_e3_lane_xrp,
    shadow_peer_lane_hud_fields,
)


def test_compute_shadow_e3_lane_xrp_balanced() -> None:
    lane = compute_shadow_e3_lane_xrp(configured_l1_xrp=11254.0)
    expected_cap = 0.07 * SHADOW_E3_PORTFOLIO_XRP_EQUIV * 0.55
    assert lane == round(expected_cap, 2)
    assert 400 <= lane <= 430


def test_shadow_peer_lane_finds_mid_band_peers() -> None:
    shadow_lane = compute_shadow_e3_lane_xrp(configured_l1_xrp=11254.0)
    runtime = {
        "our_lane_xrp": 12.0,
        "peer_lane_count": 0,
        "peer_lane_empty": True,
        "top_peers": [],
        "top_competitors": [
            {
                "account": "rPilotSmall...",
                "account_full": "rPilotSmall000000000000000000000000",
                "touch_xrp": 10.0,
                "last_spread": 0.08,
                "avg_spread": 0.09,
                "activity": 20,
                "cancels": 1,
                "sides": "b2/a2",
            },
            {
                "account": "rMidPeer123...",
                "account_full": "rMidPeer123456789012345678901234",
                "touch_xrp": shadow_lane * 0.9,
                "last_spread": 0.07,
                "avg_spread": 0.08,
                "activity": 55,
                "cancels": 2,
                "sides": "b4/a4",
            },
            {
                "account": "rWhale999...",
                "account_full": "rWhale999000000000000000000000000",
                "touch_xrp": 120000.0,
                "last_spread": 0.06,
                "avg_spread": 0.07,
                "activity": 99,
                "cancels": 0,
                "sides": "b1/a1",
            },
        ],
    }
    fields = shadow_peer_lane_hud_fields(runtime)
    assert fields["shadow_e3_lane_xrp"] == shadow_lane
    assert fields["shadow_peer_lane_count"] >= 1
    assert fields["shadow_g4_would_activate"] is True
    assert fields["live_vs_shadow_delta_peers"] >= 1
    accts = [p["account_full"] for p in fields["shadow_top_peers"]]
    assert "rMidPeer123456789012345678901234" in accts
    assert "rWhale999000000000000000000000000" not in accts


def test_shadow_grok_context_uses_shadow_lane() -> None:
    shadow_lane = compute_shadow_e3_lane_xrp(configured_l1_xrp=11254.0)
    low = shadow_lane * 0.4
    high = shadow_lane * 2.5
    state = {
        "our_lane_xrp": 12.0,
        "peer_lane_low_xrp": 4.8,
        "peer_lane_high_xrp": 30.0,
        "top_peers": [],
        "shadow_top_peers": [
            {
                "account": "rMidPeer123...",
                "account_full": "rMidPeer123456789012345678901234",
                "touch_xrp": shadow_lane * 0.95,
                "last_spread": 0.07,
                "avg_spread": 0.08,
                "activity": 40,
                "cancels": 1,
                "sides": "b3/a3",
            }
        ],
    }
    extra = {
        "analysis_context": "shadow_e3_calibration",
        "our_lane_xrp": shadow_lane,
        "peer_lane_low_xrp": low,
        "peer_lane_high_xrp": high,
        "peer_lane_count": 1,
    }
    briefing = build_competitor_analysis_context(state, "rMidPeer123456789012345678901234", extra=extra)
    assert briefing["in_peer_lane"] is True
    assert "SHADOW E3 calibration" in briefing["lane_note"]
    assert "calibration_mode=shadow_e3" in briefing["prompt_block"]
