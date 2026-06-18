"""Tests for G7 execution envelope."""

from experimental.ws_feed.execution_envelope import (
    JOIN_BACKOFF_BPS,
    PASSIVE_BACKOFF_BPS,
    compute_execution_envelope,
    touch_prices_from_backoff,
)


def test_balanced_default_8bps() -> None:
    env = compute_execution_envelope(inventory_label="balanced", g2_spread_mult=1.0)
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.inventory_posture == "balanced"


def test_xrp_heavy_ask_joins_bid_passive() -> None:
    env = compute_execution_envelope(inventory_label="xrp_heavy", g2_spread_mult=1.0)
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == JOIN_BACKOFF_BPS


def test_rlusd_heavy_bid_joins() -> None:
    env = compute_execution_envelope(inventory_label="rlusd_heavy", g2_spread_mult=1.0)
    assert env.bid_touch_backoff_bps == JOIN_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS


def test_g2_spread_mult_widens_both() -> None:
    env = compute_execution_envelope(inventory_label="balanced", g2_spread_mult=1.25)
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS * 1.25
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS * 1.25
    assert "G2 1.25" in env.summary


def test_touch_prices_never_cross() -> None:
    bid, ask = touch_prices_from_backoff(
        best_bid=1.10,
        best_ask=1.11,
        bid_backoff_bps=3.0,
        ask_backoff_bps=3.0,
    )
    assert bid <= 1.10
    assert ask >= 1.11
    assert bid < ask
