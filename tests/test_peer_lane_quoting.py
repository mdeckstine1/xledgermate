"""Tests for G4 peer-lane quoting adjustments."""

from experimental.ws_feed.peer_lane_quoting import (
    compute_g4_adjustments,
    prepare_quoting_intel,
)


def test_prepare_quoting_intel_legacy_unchanged() -> None:
    intel = prepare_quoting_intel({"competitor_pressure": 0.2})
    assert intel is not None
    assert intel["competitor_pressure"] == 0.2


def test_prepare_quoting_intel_empty_lane_neutral() -> None:
    intel = prepare_quoting_intel(
        {
            "competitor_pressure": 0.9,
            "peer_lane_count": 0,
            "peer_lane_empty": True,
        }
    )
    assert intel is not None
    assert intel["competitor_pressure"] == 0.5
    assert intel["peer_competitor_pressure"] == 0.5


def test_prepare_quoting_intel_uses_peer_pressure() -> None:
    intel = prepare_quoting_intel(
        {
            "competitor_pressure": 0.9,
            "peer_lane_count": 2,
            "peer_pressure_score": 0.25,
            "peer_observed_spread_pct": 0.08,
        }
    )
    assert intel is not None
    assert intel["competitor_pressure"] == 0.25
    assert intel["competitor_observed_spread_pct"] == 0.08


def test_g4_high_pressure_brakes_size() -> None:
    g4 = compute_g4_adjustments(
        {
            "peer_lane_count": 3,
            "peer_pressure_score": 0.8,
            "peer_fled_touch_count": 0,
        }
    )
    assert g4.active is True
    assert g4.grade == "cautious"
    assert g4.size_mult < 1.0
    assert g4.size_mult == 0.92


def test_g4_fled_touch_ask_bias_when_xrp_heavy() -> None:
    g4 = compute_g4_adjustments(
        {
            "peer_lane_count": 2,
            "peer_pressure_score": 0.2,
            "peer_fled_touch_count": 2,
        },
        inventory_skew=0.25,
        inventory_label="xrp_heavy",
    )
    assert g4.grade == "skim"
    assert g4.ask_size_mult > 1.0
    assert g4.bid_size_mult == 1.0


def test_g4_empty_lane_neutral() -> None:
    g4 = compute_g4_adjustments({"peer_lane_empty": True, "peer_lane_count": 0})
    assert g4.grade == "empty_lane"
    assert g4.size_mult == 1.0
    assert g4.active is False
