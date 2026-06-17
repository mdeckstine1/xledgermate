"""Tests for I6 regime vs peer HUD fields."""

from experimental.ws_feed.hud_intel_support import regime_intel_hud_fields


def test_regime_split_peer_lane_active() -> None:
    runtime = {
        "peer_lane_count": 2,
        "competitor_intel": {
            "peer_pressure_score": 0.35,
            "book_regime_pressure": 0.72,
            "peer_observed_spread_pct": 0.20,
        },
        "book_spread_pct": 0.18,
    }
    fields = regime_intel_hud_fields(runtime)
    assert fields["peer_pressure"] == 0.35
    assert fields["book_regime_pressure"] == 0.72
    assert fields["spread_regime_gap_bps"] == 2.0


def test_regime_split_empty_peer_lane_uses_book_pressure() -> None:
    runtime = {
        "peer_lane_count": 0,
        "competitor_intel": {
            "competitor_pressure": 0.61,
            "competitor_observed_spread_pct": 0.22,
        },
        "book_spread_pct": 0.20,
    }
    fields = regime_intel_hud_fields(runtime)
    assert fields["peer_pressure"] is None
    assert fields["book_regime_pressure"] == 0.61
    assert fields["spread_regime_gap_bps"] == 2.0
