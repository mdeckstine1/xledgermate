from experimental.ws_feed.as_safety import (
    enforce_reservation_gate,
    sacred_reservation_inside_l1,
)


def test_sacred_inside() -> None:
    assert sacred_reservation_inside_l1(reservation=1.005, best_bid=1.0, best_ask=1.01)


def test_sacred_outside() -> None:
    assert not sacred_reservation_inside_l1(reservation=0.99, best_bid=1.0, best_ask=1.01)


def test_enforce_corrects_mismatch() -> None:
    result = enforce_reservation_gate(
        would_quote_reservation=True,
        reservation=0.99,
        best_bid=1.0,
        best_ask=1.01,
        context="test",
    )
    assert result is False
