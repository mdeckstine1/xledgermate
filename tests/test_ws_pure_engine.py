"""Tests for WS pure production engine helpers."""

from connectors.xrpl_connector import OpenOffer
from engine.order_sync import plan_order_sync
from experimental.ws_feed.ws_pure_engine import (
    WsPureTradingEngine,
    pure_intents_to_quote_intents,
)


def test_plan_order_sync_empty_intents_cancels_all() -> None:
    offers = [
        OpenOffer(sequence=1, side="bid", price=1.1, size_xrp=10.0),
        OpenOffer(sequence=2, side="ask", price=1.11, size_xrp=10.0),
    ]
    plan = plan_order_sync([], offers, best_bid=1.1, best_ask=1.11)
    assert plan.cancel_sequences == [1, 2]
    assert plan.place_intents == []


def test_execution_summary_pull_when_blocked() -> None:
    from config.settings import BotConfig

    eng = WsPureTradingEngine(BotConfig.load())
    msg = eng._execution_summary(
        eng.config, 0, cancelled=2, would_sync=0, would_quote=False
    )
    assert "pulled 2" in msg


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
