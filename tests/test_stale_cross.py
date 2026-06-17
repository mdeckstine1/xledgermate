"""Tests for M3 stale-cross helper."""

from experimental.ws_feed.stale_cross import detect_stale_cross, reservation_inside_l1


def test_reservation_inside_l1() -> None:
    assert reservation_inside_l1(1.28, 1.279, 1.281) is True
    assert reservation_inside_l1(1.282, 1.279, 1.281) is False


def test_detect_stale_cross_true() -> None:
    crossed = detect_stale_cross(
        reservation=1.280,
        best_bid_before=1.279,
        best_ask_before=1.281,
        best_bid_after=1.280,
        best_ask_after=1.282,
    )
    assert crossed is True


def test_detect_stale_cross_false_when_still_inside() -> None:
    assert not detect_stale_cross(
        reservation=1.280,
        best_bid_before=1.279,
        best_ask_before=1.282,
        best_bid_after=1.279,
        best_ask_after=1.282,
    )
