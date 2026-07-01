"""Tests for CLOB+AMM fill walk simulation."""

from __future__ import annotations

from pathlib import Path

from experimental.arb.book_provider import BookLevel, TokenXrpBookDepth
from experimental.arb.fill_simulator import (
    AmmPool,
    amm_swap_rlusd_for_xrp,
    amm_swap_xrp_for_rlusd,
    best_roundtrip,
    simulate_from_soak_row,
    simulate_rlusd_xrp_roundtrip,
    walk_asks_buy_xrp,
    walk_bids_sell_xrp,
)


def _book() -> TokenXrpBookDepth:
    bids = (
        BookLevel(1.10, 100.0),
        BookLevel(1.09, 200.0),
    )
    asks = (
        BookLevel(1.11, 80.0),
        BookLevel(1.12, 150.0),
    )
    return TokenXrpBookDepth(
        best_bid=1.10,
        best_ask=1.11,
        mid=1.105,
        spread_pct=0.9,
        bids=bids,
        asks=asks,
    )


def _pool() -> AmmPool:
    return AmmPool(xrp_reserve=50_000.0, rlusd_reserve=52_500.0, fee_bps=10.0)


def test_walk_asks_partial_level() -> None:
    xrp, spent, avg = walk_asks_buy_xrp(_book().asks, 50.0)
    assert spent == 50.0
    assert abs(xrp - 50.0 / 1.11) < 1e-6
    assert avg is not None
    assert abs(avg - 1.11) < 1e-6


def test_walk_bids_full_fill() -> None:
    rlusd, sold, avg = walk_bids_sell_xrp(_book().bids, 50.0)
    assert sold == 50.0
    assert abs(rlusd - 55.0) < 1e-6
    assert avg == 1.10


def test_amm_swap_reduces_reserve() -> None:
    pool = _pool()
    xrp_out, new_pool = amm_swap_rlusd_for_xrp(pool, 1000.0)
    assert xrp_out > 0
    assert new_pool.rlusd_reserve > pool.rlusd_reserve
    assert new_pool.xrp_reserve < pool.xrp_reserve
    rlusd_out, _ = amm_swap_xrp_for_rlusd(new_pool, xrp_out)
    assert rlusd_out > 0


def test_roundtrip_amm_cheaper_can_profit_when_spread_wide() -> None:
    book = TokenXrpBookDepth(
        best_bid=1.12,
        best_ask=1.13,
        mid=1.125,
        spread_pct=0.88,
        bids=(BookLevel(1.12, 500.0),),
        asks=(BookLevel(1.13, 500.0),),
    )
    pool = AmmPool(xrp_reserve=50_000.0, rlusd_reserve=55_000.0, fee_bps=5.0)  # mid 1.10
    sim = simulate_rlusd_xrp_roundtrip(
        notional_rlusd=200.0,
        book=book,
        pool=pool,
        direction="amm_cheaper",
    )
    assert sim.feasible
    assert sim.direction == "amm_cheaper"
    assert sim.profit_bps > 0


def test_simulate_from_soak_row() -> None:
    row = {
        "status": "ok",
        "clob_mid_rlusd_per_xrp": 1.12,
        "amm_mid_rlusd_per_xrp": 1.10,
        "amm_fee_bps": 10.0,
        "amm_xrp_reserve": 50_000.0,
        "amm_rlusd_reserve": 55_000.0,
        "book_depth": {
            "best_bid": 1.12,
            "best_ask": 1.13,
            "mid": 1.125,
            "spread_pct": 0.88,
            "bids": [{"p": 1.12, "x": 500.0}],
            "asks": [{"p": 1.13, "x": 500.0}],
        },
    }
    sim = simulate_from_soak_row(row, notional_rlusd=500.0)
    assert sim is not None
    assert sim.feasible
    assert sim.profit_bps > 0


def test_live_fill_simulation_payload() -> None:
    from experimental.arb.fill_simulator import build_arb_fill_simulation_payload

    row = {
        "status": "ok",
        "clob_mid_rlusd_per_xrp": 1.12,
        "amm_mid_rlusd_per_xrp": 1.10,
        "spread_bps": 18.0,
        "clob_spread_pct": 0.1,
        "amm_fee_bps": 5.0,
        "amm_xrp_reserve": 50_000.0,
        "amm_rlusd_reserve": 55_000.0,
        "book_depth": {
            "best_bid": 1.12,
            "best_ask": 1.13,
            "mid": 1.125,
            "spread_pct": 0.88,
            "bids": [{"p": 1.12, "x": 500.0}],
            "asks": [{"p": 1.13, "x": 500.0}],
        },
    }
    payload = build_arb_fill_simulation_payload(latest=row, logs_dir=Path("."))
    live = payload["live"]
    assert live["available"] is True
    assert len(live["rows"]) == 3
    assert live["rows"][0]["notional_rlusd"] == 500.0
