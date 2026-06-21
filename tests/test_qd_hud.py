"""Tests for layered QD HUD field enrichment."""

from __future__ import annotations

from experimental.ws_feed.qd_hud import (
    QD_HUD_VERSION,
    build_qd_decision_summary,
    build_qd_hud_fields,
    build_qd_snapshot,
)


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
            "qd_inventory_cb_mode": "skipped_solo",
            "qd_inventory_cb_note": "L5 inventory CB skipped — solo defers to L2 intent",
            "qd_layer_trace": "trace book=solo drift=heavy_xrp intent=solo_accumulate_on_edge",
        }
    )
    assert fields["qd_hud_version"] == QD_HUD_VERSION
    assert fields["qd_posture_class"] == "good"
    assert fields["qd_peer_lane_token"] == "empty"
    assert fields["qd_inventory_cb_mode"] == "skipped_solo"
    assert "bid=ON" in fields["qd_permissions_summary"]
    summary = fields["qd_decision_summary"]
    assert summary["health"] == "good"
    assert summary["posture_badge"] == "SOLO"
    assert summary["solo_accumulate"] is True
    assert summary["quoting_short"] == "B ON / A OFF"
    assert "skipped (solo)" in summary["inventory_cb_line"]
    assert "peer empty" in summary["posture_detail"]
    snap = fields["qd_snapshot"]
    assert snap["intent_label"] == "ACCUMULATE ON EDGE"
    assert snap["layer_trace_struct"]["l1"].startswith("solo")
    assert "edge B" in snap["intent_subtext"]


def test_build_qd_hud_fields_crowded_inventory_cb() -> None:
    fields = build_qd_hud_fields(
        {
            "qd_intent": "two_sided_skim",
            "qd_book_mode": "crowded",
            "qd_drift_band": "heavy_xrp",
            "solo_mode": False,
            "peer_lane_empty": False,
            "peer_lane_count": 3,
            "posture_reason": "crowded_default",
            "qd_peer_lane_token": "crowded",
            "qd_bid_allowed": False,
            "qd_ask_allowed": True,
            "qd_bid_pause_cause": "inventory",
            "qd_ask_pause_cause": "",
            "qd_bid_edge_viable": True,
            "qd_ask_edge_viable": True,
            "qd_inventory_cb_mode": "blocked_bid",
            "qd_inventory_cb_note": "inventory bailout: +17% XRP drift (cap 12%) → pause bids",
            "qd_heavy_drift_l5_deferred": True,
        }
    )
    summary = fields["qd_decision_summary"]
    assert summary["posture_badge"] == "CROWDED"
    assert "crowded (3)" in summary["posture_detail"]
    assert "active — bid blocked" in summary["inventory_cb_line"]
    assert "heavy drift" in summary["inventory_cb_line"]
    snap = fields["qd_snapshot"]
    assert snap["heavy_drift_l5_deferred"] is True


def test_build_qd_hud_fields_solo_trim_no_edge() -> None:
    fields = build_qd_hud_fields(
        {
            "qd_intent": "inventory_unload",
            "qd_book_mode": "solo",
            "qd_drift_band": "heavy_xrp",
            "solo_mode": True,
            "peer_lane_empty": True,
            "peer_lane_count": 0,
            "posture_reason": "confirmed_empty",
            "qd_bid_allowed": False,
            "qd_ask_allowed": False,
            "qd_bid_edge_viable": False,
            "qd_ask_edge_viable": False,
            "qd_bid_pause_cause": "edge",
            "qd_ask_pause_cause": "edge",
            "qd_intent_reason": "solo + xrp drift + no edge — trim only (ask)",
        }
    )
    summary = fields["qd_decision_summary"]
    assert summary["intent_line"].startswith("INVENTORY UNLOAD")
    assert "trim-only" in summary["intent_subtext"]
    assert summary["inventory_cb_line"].startswith("Inv CB: skipped (solo)")


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
    assert fields["qd_decision_summary"]["health"] == "protect"
    assert fields["qd_decision_summary"]["protection_active"] is True


def test_build_qd_hud_fields_missing_intel_synthesis() -> None:
    fields = build_qd_hud_fields({"inventory_label": "balanced"})
    assert fields["posture_reason"] == "missing_intel"
    assert fields["qd_peer_lane_token"] == "missing"
    assert fields["qd_book_mode"] == "crowded"
    assert fields["qd_decision_summary"]["posture_badge"] == "CROWDED?"


def test_build_qd_decision_summary_both_blocked_edge() -> None:
    runtime = {
        "qd_intent": "solo_accumulate_on_edge",
        "qd_book_mode": "solo",
        "qd_drift_band": "heavy_xrp",
        "solo_mode": True,
        "posture_reason": "confirmed_empty",
        "peer_lane_count": 0,
        "qd_bid_allowed": False,
        "qd_ask_allowed": False,
        "qd_bid_edge_viable": False,
        "qd_ask_edge_viable": False,
        "qd_bid_pause_cause": "edge",
        "qd_ask_pause_cause": "edge",
        "qd_bid_implied_bps": 1.4,
        "qd_ask_implied_bps": 1.4,
        "qd_bid_min_edge_bps": 2.0,
        "qd_ask_min_edge_bps": 2.0,
    }
    snap = build_qd_snapshot(runtime)
    summary = build_qd_decision_summary(runtime, snap)
    assert summary["health"] == "caution"
    assert summary["primary_block"] == "Edge Gate"
    assert summary["quoting_active"] is False
    assert "BID OFF" in summary["quoting_line"]
