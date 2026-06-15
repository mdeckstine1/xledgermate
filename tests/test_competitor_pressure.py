"""Tests for formal competitor pressure -> A-S input mapping."""

from experimental.competitor_pressure import (
    CompetitorPressure,
    apply_competitor_pressure,
    from_intel_dict,
)


def test_low_pressure_more_aggressive_than_high() -> None:
    low = apply_competitor_pressure(
        CompetitorPressure(0.1, observed_l1_spread_pct=0.08),
        base_volatility_pct=1.0,
        base_book_spread_pct=0.12,
    )
    high = apply_competitor_pressure(
        CompetitorPressure(0.9),
        base_volatility_pct=1.0,
        base_book_spread_pct=0.12,
    )
    assert low.volatility_pct < high.volatility_pct
    assert low.size_mult > high.size_mult
    assert low.gamma_scale < high.gamma_scale


def test_low_pressure_uses_observed_spread_when_tighter() -> None:
    adj = apply_competitor_pressure(
        CompetitorPressure(0.2, observed_l1_spread_pct=0.06),
        base_volatility_pct=0.5,
        base_book_spread_pct=0.12,
    )
    assert adj.book_spread_pct == 0.06


def test_xrp_heavy_uses_ask_pressure() -> None:
    pressure = CompetitorPressure(value=0.8, ask_pressure=0.15)
    adj = apply_competitor_pressure(
        pressure,
        base_volatility_pct=1.0,
        base_book_spread_pct=0.10,
        inventory_skew=0.30,
    )
    assert adj.effective_pressure == 0.15
    assert adj.volatility_pct < 1.0


def test_from_intel_dict() -> None:
    p = from_intel_dict({"competitor_pressure": 0.25, "competitor_observed_spread_pct": 0.09})
    assert p is not None
    assert p.value == 0.25
    assert p.observed_l1_spread_pct == 0.09
