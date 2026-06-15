"""Tests for B3 WS book age modulator."""

from experimental.ws_feed.ws_book_age_modulator import apply_ws_book_age_modulator


def test_stale_book_raises_vol() -> None:
    base = 0.10
    fresh = apply_ws_book_age_modulator(base_volatility_pct=base, ws_book_age_s=2.0)
    stale = apply_ws_book_age_modulator(base_volatility_pct=base, ws_book_age_s=30.0)
    assert stale.volatility_pct > fresh.volatility_pct
    assert stale.vol_mult > 1.0
    assert stale.tag == "STALE"
    assert "BOOK_AGE" in stale.rationale


def test_fresh_low_pressure_allows_aggression() -> None:
    neutral = apply_ws_book_age_modulator(
        base_volatility_pct=0.10,
        ws_book_age_s=1.0,
        competitor_pressure=0.55,
    )
    aggressive = apply_ws_book_age_modulator(
        base_volatility_pct=0.10,
        ws_book_age_s=1.0,
        competitor_pressure=0.15,
    )
    assert aggressive.volatility_pct < neutral.volatility_pct
    assert aggressive.size_mult > 1.0
    assert aggressive.tag == "FRESH+LOW_P"


def test_mid_age_neutral_mult() -> None:
    mid = apply_ws_book_age_modulator(base_volatility_pct=0.12, ws_book_age_s=8.0)
    assert mid.vol_mult == 1.0
    assert mid.size_mult == 1.0
    assert mid.tag == "NEUTRAL"
