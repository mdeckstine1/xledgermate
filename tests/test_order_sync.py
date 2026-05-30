"""Selective order refresh planning tests."""

from core.runtime_state import QuoteIntent
from connectors.xrpl_connector import OpenOffer
from engine.order_sync import plan_order_sync


def test_plan_keeps_matching_offer() -> None:
    intents = [
        QuoteIntent(level=1, side="ask", price=1.34, size_xrp=50.0),
    ]
    offers = [OpenOffer(sequence=99, side="ask", price=1.3401, size_xrp=50.0)]
    plan = plan_order_sync(intents, offers, price_tolerance_pct=0.08, size_tolerance_xrp=0.75)
    assert plan.kept_count == 1
    assert plan.cancel_sequences == []
    assert plan.place_intents == []


def test_plan_replaces_when_price_moves() -> None:
    intents = [
        QuoteIntent(level=1, side="bid", price=1.30, size_xrp=50.0),
    ]
    offers = [OpenOffer(sequence=7, side="bid", price=1.28, size_xrp=50.0)]
    plan = plan_order_sync(intents, offers)
    assert plan.kept_count == 0
    assert plan.cancel_sequences == [7]
    assert len(plan.place_intents) == 1
