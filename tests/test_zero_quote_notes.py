"""Tests for B4 zero-quote operator notes."""

from experimental.ws_feed.zero_quote_notes import (
    build_tight_book_advisory,
    classify_and_explain_pure_zero_quote,
    spread_floor_binding,
)


def test_spread_floor_binding_at_floor() -> None:
    assert spread_floor_binding(0.04, 0.04) is True
    assert spread_floor_binding(0.10, 0.04) is False


def test_tight_ok_when_quoting_despite_wider_optimal() -> None:
    msg = build_tight_book_advisory(
        would_quote=True,
        zero_quote_reason="quoted",
        reservation=1.113,
        best_bid=1.112,
        best_ask=1.114,
        book_spread_pct=0.15,
        optimal_spread_pct=0.175,
        min_spread_floor_pct=0.04,
    )
    assert "TIGHT OK" in msg
    assert "optimal 0.175%" in msg


def test_blocked_reservation_outside() -> None:
    _, detail, op = classify_and_explain_pure_zero_quote(
        would_quote=False,
        best_bid=1.120,
        best_ask=1.122,
        reservation=1.1195,
        book_spread_pct=0.15,
        optimal_spread_pct=0.18,
        min_spread_floor_pct=0.04,
    )
    assert op.startswith("BLOCKED")
    assert "reservation" in op.lower()
    assert "below bid" in op.lower() or "<=" in detail


def test_blocked_optimal_wider_than_book() -> None:
    reason, detail, op = classify_and_explain_pure_zero_quote(
        would_quote=False,
        best_bid=1.120,
        best_ask=1.122,
        reservation=1.121,
        book_spread_pct=0.10,
        optimal_spread_pct=0.20,
        min_spread_floor_pct=0.04,
    )
    assert reason == "optimal_spread_wider_than_book"
    assert "gap" in detail
    assert "BLOCKED" in op
