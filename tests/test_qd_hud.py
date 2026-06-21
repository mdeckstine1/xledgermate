"""Tests for layered QD HUD field enrichment."""

from __future__ import annotations

from experimental.ws_feed.qd_hud import QD_HUD_VERSION, build_qd_hud_fields


def test_build_qd_hud_fields_solo_accumulate() -> None:
    fields = build_qd_hud_fields(
        {
            "qd_intent": "solo_accumulate_on_edge",
            "qd_book_mode": "solo",
            "qd_drift_band": "heavy_xrp",
            "solo_mode": True,
            "peer_lane_empty": True,
            "peer_lane_count": 0,
            "posture_reason": "confirmed_empty",
            "qd_peer_lane_token": "empty",
            "qd_bid_allowed": True,
            "qd_ask_allowed": False,
            "qd_bid_edge_viable": True,
            "qd_ask_edge_viable": False,
            "qd_bid_implied_bps": 4.2,
            "qd_ask_implied_bps": 1.0,
            "qd_bid_size_mult": 1.0,
            "qd_ask_size_mult": 0.0,
            "qd_layer_trace": "trace book=solo drift=heavy_xrp intent=solo_accumulate_on_edge",
        }
    )
    assert fields["qd_hud_version"] == QD_HUD_VERSION
    assert fields["qd_posture_class"] == "good"
    assert fields["qd_peer_lane_token"] == "empty"
    assert "bid=ON" in fields["qd_permissions_summary"]


def test_build_qd_hud_fields_bleed_bad_class() -> None:
    fields = build_qd_hud_fields(
        {
            "qd_book_mode": "solo",
            "solo_mode": True,
            "qd_intent": "patient_solo",
            "qd_bid_bleeding": True,
            "qd_bid_pause_cause": "bleed",
            "peer_lane_empty": True,
            "peer_lane_count": 0,
            "competitor_intel": {"peer_lane_count": 0, "peer_lane_empty": True},
        }
    )
    assert fields["qd_posture_class"] == "bad"


def test_build_qd_hud_fields_missing_intel_synthesis() -> None:
    fields = build_qd_hud_fields({"inventory_label": "balanced"})
    assert fields["posture_reason"] == "missing_intel"
    assert fields["qd_peer_lane_token"] == "missing"
    assert fields["qd_book_mode"] == "crowded"
