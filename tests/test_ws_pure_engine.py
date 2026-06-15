"""Tests for WS pure production engine helpers."""

from experimental.ws_feed.ws_pure_engine import pure_intents_to_quote_intents


def test_pure_intents_active_l1_only() -> None:
    ladder = [
        {"level": 1, "side": "bid", "price": 1.1, "size_xrp": 12.0, "active": True},
        {"level": 1, "side": "ask", "price": 1.11, "size_xrp": 12.0, "active": True},
        {"level": 2, "side": "bid", "price": 1.09, "size_xrp": 8.0, "active": False},
    ]
    intents = pure_intents_to_quote_intents(ladder, would_quote=True)
    assert len(intents) == 2
    assert {i.side for i in intents} == {"bid", "ask"}


def test_pure_intents_empty_when_blocked() -> None:
    ladder = [
        {"level": 1, "side": "bid", "price": 1.1, "size_xrp": 12.0, "active": True},
    ]
    assert pure_intents_to_quote_intents(ladder, would_quote=False) == []
