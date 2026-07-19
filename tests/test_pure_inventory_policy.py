"""Tests for WS pure inventory policy (limits + pause sides)."""

import asyncio

from experimental.ws_feed.pure_inventory_policy import (
    apply_pause_to_ladder,
    apply_pure_inventory_policy,
    count_active_l1_quotes,
)
from experimental.ws_feed.pure_quote_path import PureQuotePath


def test_rlusd_heavy_pauses_asks_and_zeros_ask_size() -> None:
    # ~20% XRP vs 55% target at mid ~1.28
    result = apply_pure_inventory_policy(
        bid_size_xrp=3.0,
        ask_size_xrp=3.0,
        xrp_balance=50.0,
        rlusd_balance=230.0,
        mid_price=1.28,
        target_xrp_ratio=0.55,
        inventory_max_deviation=0.12,
        inventory_mode="market_make",
        xrp_reserve=12.0,
        inventory_overshoot_slack=0.03,
        min_order_size_xrp=1.0,
        bid_size_mult=1.45,
        ask_size_mult=0.25,
    )
    assert result.pause_asks is True
    assert result.pause_bids is False
    assert result.ask_size_xrp == 0.0
    assert result.bid_size_xrp > 3.0


def test_xrp_heavy_pauses_bids() -> None:
    result = apply_pure_inventory_policy(
        bid_size_xrp=10.0,
        ask_size_xrp=10.0,
        xrp_balance=180.0,
        rlusd_balance=20.0,
        mid_price=1.10,
        target_xrp_ratio=0.55,
        inventory_max_deviation=0.12,
        inventory_mode="market_make",
        xrp_reserve=12.0,
        inventory_overshoot_slack=0.03,
        min_order_size_xrp=1.0,
        bid_size_mult=0.25,
        ask_size_mult=1.45,
    )
    assert result.pause_bids is True
    assert result.pause_asks is False
    assert result.bid_size_xrp == 0.0
    assert result.ask_size_xrp > 0.0


def test_qd_mode_rlusd_heavy_bid_cap_stops_at_target() -> None:
    result = apply_pure_inventory_policy(
        bid_size_xrp=100.0,
        ask_size_xrp=100.0,
        xrp_balance=40.0,
        rlusd_balance=160.0,
        mid_price=1.0,
        target_xrp_ratio=0.55,
        inventory_max_deviation=0.12,
        inventory_mode="market_make",
        xrp_reserve=12.0,
        inventory_overshoot_slack=0.03,
        min_order_size_xrp=1.0,
        bid_size_mult=1.0,
        ask_size_mult=1.0,
        apply_side_pauses=False,
    )
    assert result.pause_asks is True
    assert result.pause_bids is False
    assert result.bid_size_xrp == 70.0


def test_qd_mode_xrp_heavy_ask_cap_stops_at_target() -> None:
    result = apply_pure_inventory_policy(
        bid_size_xrp=100.0,
        ask_size_xrp=100.0,
        xrp_balance=160.0,
        rlusd_balance=40.0,
        mid_price=1.0,
        target_xrp_ratio=0.55,
        inventory_max_deviation=0.12,
        inventory_mode="market_make",
        xrp_reserve=12.0,
        inventory_overshoot_slack=0.03,
        min_order_size_xrp=1.0,
        bid_size_mult=1.0,
        ask_size_mult=1.0,
        apply_side_pauses=False,
    )
    assert result.pause_bids is True
    assert result.pause_asks is False
    assert result.ask_size_xrp == 50.0


def test_pause_to_ladder_deactivates_ask_l1() -> None:
    ladder = [
        {"level": 1, "side": "bid", "price": 1.1, "size_xrp": 5.0, "active": True, "planned": False},
        {"level": 1, "side": "ask", "price": 1.11, "size_xrp": 5.0, "active": True, "planned": False},
    ]
    out = apply_pause_to_ladder(ladder, block_bids=False, block_asks=True, min_order_size_xrp=1.0)
    bid = next(i for i in out if i["side"] == "bid")
    ask = next(i for i in out if i["side"] == "ask")
    assert bid["active"] is True
    assert ask["active"] is False
    assert count_active_l1_quotes(out) == 1


def test_pure_quote_path_rlusd_heavy_bid_only_intents() -> None:
    async def run() -> None:
        path = PureQuotePath(configured_l1_xrp=15.0, min_order_size_xrp=1.0)
        dec = await path.compute_decision(
            mid=1.28,
            best_bid=1.279,
            best_ask=1.281,
            xrp_bal=50.0,
            rlusd_bal=230.0,
            target_ratio=0.55,
            inventory_max_deviation=0.12,
        )
        assert dec.qd_bid_allowed is True
        assert dec.qd_ask_allowed is False
        active = [i for i in dec.quote_intents if i.get("active")]
        assert all(i["side"] == "bid" for i in active)
        assert dec.ask_size == 0.0
        assert dec.bid_size >= 1.0

    asyncio.run(run())
