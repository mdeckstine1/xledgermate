"""Tests for A2.3c ask brake cancel."""

from types import SimpleNamespace

from experimental.ws_feed.ask_brake_cancel import ask_brake_cancel_sequences


def test_no_cancel_when_asks_allowed() -> None:
    offers = [SimpleNamespace(side="ask", sequence=1)]
    assert ask_brake_cancel_sequences(offers, pause_asks=False) == []


def test_cancel_all_asks_when_paused() -> None:
    offers = [
        SimpleNamespace(side="bid", sequence=10),
        SimpleNamespace(side="ask", sequence=11),
        SimpleNamespace(side="ask", sequence=12),
    ]
    assert ask_brake_cancel_sequences(offers, pause_asks=True) == [11, 12]
