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


def test_plan_keeps_competitive_touch_queue_when_intent_moves() -> None:
    """Join-touch intents may drift with the book; keep offers still at the touch."""
    intents = [
        QuoteIntent(level=1, side="bid", price=1.336600, size_xrp=50.0),
        QuoteIntent(level=1, side="ask", price=1.337200, size_xrp=50.0),
    ]
    offers = [
        OpenOffer(sequence=11, side="bid", price=1.336489, size_xrp=50.0),
        OpenOffer(sequence=12, side="ask", price=1.337077, size_xrp=50.0),
    ]
    plan = plan_order_sync(
        intents,
        offers,
        price_tolerance_pct=0.07,
        size_tolerance_xrp=0.50,
        best_bid=1.336489,
        best_ask=1.337077,
        max_worse_than_touch_pct=0.50,
        preserve_queue_max_worse_pct=0.50,
        preserve_touch_queue=True,
    )
    assert plan.kept_count == 2
    assert plan.cancel_sequences == []
    assert plan.place_intents == []


def test_preserve_queue_rejects_stale_off_touch_bid() -> None:
    intents = [QuoteIntent(level=1, side="bid", price=1.347400, size_xrp=35.0)]
    offers = [OpenOffer(sequence=11, side="bid", price=1.344757, size_xrp=35.0)]
    plan = plan_order_sync(
        intents,
        offers,
        best_bid=1.347400,
        best_ask=1.348338,
        preserve_queue_max_worse_pct=0.08,
        preserve_touch_queue=True,
    )
    assert plan.kept_count == 0
    assert plan.cancel_sequences == [11]
    assert len(plan.place_intents) == 1


def test_offers_off_touch_detects_stale_bid() -> None:
    from engine.order_sync import offers_off_touch

    offers = [OpenOffer(sequence=1, side="bid", price=1.344757, size_xrp=35.0)]
    assert offers_off_touch(
        offers, best_bid=1.347400, best_ask=1.348338, max_worse_than_touch_pct=0.08
    )
