"""Tests for F2 HUD advisory stub."""

from experimental.ws_feed.ai_advisory_hud import (
    advisory_hud_fields,
    derive_advisory_signal,
    reset_advisory_cache,
)


def test_derive_advisory_low_pressure_skim_harder() -> None:
    sig = derive_advisory_signal({"competitor_pressure": 0.12, "peer_lane_count": 0})
    assert sig.skim_harder is True
    assert sig.vol_mult < 1.0
    assert sig.size_mult > 1.0


def test_advisory_rate_limit_cache() -> None:
    reset_advisory_cache()
    runtime = {"competitor_pressure": 0.1, "peer_lane_count": 0}
    first = advisory_hud_fields(runtime, min_interval_s=9999.0, now=100.0)
    runtime["competitor_pressure"] = 0.9
    second = advisory_hud_fields(runtime, min_interval_s=9999.0, now=150.0)
    assert first["ai_advisory_skim_harder"] == second["ai_advisory_skim_harder"]
