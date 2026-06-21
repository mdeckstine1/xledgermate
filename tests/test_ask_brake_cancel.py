"""Tests for QD side-brake cancel."""

from types import SimpleNamespace

from experimental.ws_feed.ask_brake_cancel import side_brake_cancel_sequences


def test_no_cancel_when_both_allowed() -> None:
    offers = [SimpleNamespace(side="ask", sequence=1)]
    assert side_brake_cancel_sequences(offers, bid_allowed=True, ask_allowed=True) == []


def test_cancel_asks_when_blocked() -> None:
    offers = [
        SimpleNamespace(side="bid", sequence=10),
        SimpleNamespace(side="ask", sequence=11),
        SimpleNamespace(side="ask", sequence=12),
    ]
    assert side_brake_cancel_sequences(
        offers, bid_allowed=True, ask_allowed=False
    ) == [11, 12]


def test_cancel_bids_when_blocked() -> None:
    offers = [
        SimpleNamespace(side="bid", sequence=10),
        SimpleNamespace(side="ask", sequence=11),
    ]
    assert side_brake_cancel_sequences(
        offers, bid_allowed=False, ask_allowed=True
    ) == [10]
