"""Tests for spread capture estimation."""

from __future__ import annotations

from monitoring.fill_economics import spread_capture_from_fill_row
from monitoring.fill_detection import detect_fill_from_balance_delta


def test_spread_capture_floor_when_fill_at_mid() -> None:
    cap = spread_capture_from_fill_row(
        {
            "side": "BUY",
            "xrp_amount": "10.0",
            "rlusd_amount": "11.9",
            "price_rlusd_per_xrp": "1.19",
            "profit_xrp_equiv": "0",
            "notes": "WS pure fill @ mid 1.190000",
        },
        default_half_spread_bps=10.0,
    )
    assert cap == 0.01


def test_spread_capture_uses_stored_when_present() -> None:
    cap = spread_capture_from_fill_row(
        {
            "side": "SELL",
            "xrp_amount": "10.0",
            "rlusd_amount": "12.0",
            "price_rlusd_per_xrp": "1.2",
            "profit_xrp_equiv": "0.042",
            "notes": "",
        }
    )
    assert cap == 0.042


def test_spread_capture_skips_incoherent_artifact_row() -> None:
    cap = spread_capture_from_fill_row(
        {
            "side": "SELL",
            "xrp_amount": "0.999970",
            "rlusd_amount": "27.856938",
            "price_rlusd_per_xrp": "27.857774",
            "profit_xrp_equiv": "23.018669",
            "notes": "WS pure fill (balance delta); capture ~+23.0187 XRP @ mid 1.159805",
        }
    )
    assert cap == 0.0


def test_spread_capture_skips_legacy_row_without_mid_anchor() -> None:
    """Rows without @ mid still use stored profit (legacy); grading filters separately."""
    cap = spread_capture_from_fill_row(
        {
            "side": "SELL",
            "xrp_amount": "10.0",
            "rlusd_amount": "12.0",
            "price_rlusd_per_xrp": "1.2",
            "profit_xrp_equiv": "0.042",
            "notes": "WS pure fill (balance delta); capture ~+0.0420 XRP",
        }
    )
    assert cap == 0.042


def test_detect_fill_uses_implied_price_when_both_legs_move() -> None:
    fill = detect_fill_from_balance_delta(
        prev_xrp=100.0,
        prev_rlusd=200.0,
        curr_xrp=90.0,
        curr_rlusd=211.9,
        mid_price=1.19,
    )
    assert fill is not None
    assert fill["side"] == "SELL"
    assert abs(fill["price_rlusd_per_xrp"] - (11.9 / 10.0)) < 1e-6
