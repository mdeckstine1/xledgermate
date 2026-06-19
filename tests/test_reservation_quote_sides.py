"""Tests for one-sided MM posture when reservation sits outside L1."""

from __future__ import annotations

import asyncio

from experimental.ws_feed.pure_quote_path import PureQuotePath
from experimental.ws_feed.reservation_metrics import reservation_quote_sides


def test_reservation_quote_sides_inside() -> None:
    bid, ask, posture = reservation_quote_sides(
        reservation=1.10, best_bid=1.099, best_ask=1.101
    )
    assert posture == "inside"
    assert bid and ask


def test_reservation_quote_sides_below_bid_ask_only() -> None:
    bid, ask, posture = reservation_quote_sides(
        reservation=1.282670, best_bid=1.282800, best_ask=1.283100
    )
    assert posture == "below_bid"
    assert bid is False
    assert ask is True


def test_reservation_quote_sides_above_ask_bid_only() -> None:
    bid, ask, posture = reservation_quote_sides(
        reservation=1.1015, best_bid=1.099, best_ask=1.101
    )
    assert posture == "above_ask"
    assert bid is True
    assert ask is False


def test_rlusd_heavy_bid_only_when_reservation_below_bid() -> None:
    """VPS rlusd_heavy: reservation below bid but inventory needs bid-only rebalance."""
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.282920,
            best_bid=1.282850,
            best_ask=1.283000,
            xrp_bal=55.74,
            rlusd_bal=225.82,
            target_ratio=0.55,
        )
        assert d.would_quote is True
        assert d.zero_quote_reason == "quoted"
        assert d.quote_count == 1
        assert d.suggested_bid is not None
        assert d.suggested_ask is None
        assert "rebalance" in d.quoting_policy_label.lower()
        active = [i for i in d.quote_intents if i.get("active")]
        assert len(active) == 1
        assert active[0]["side"] == "bid"

    asyncio.run(run())


def test_neutral_inventory_ask_only_when_reservation_below_bid() -> None:
    """When inventory neutral, reservation below bid → ask-only skew."""
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.282920,
            best_bid=1.282850,
            best_ask=1.283000,
            xrp_bal=127.0,
            rlusd_bal=127.0 * 1.282920,
            target_ratio=0.55,
        )
        assert d.would_quote is True
        assert d.quote_count == 1
        assert d.suggested_ask is not None
        assert d.suggested_bid is None
        active = [i for i in d.quote_intents if i.get("active")]
        assert active[0]["side"] == "ask"

    asyncio.run(run())
