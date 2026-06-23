"""Tests for shared stale pending-buy policy."""

from __future__ import annotations

from alpha.hud.skynet import build_skynet_context
from alpha.orders.stale_pending import (
    build_pending_buy_stale_snapshot,
    stale_pending_buy_reason,
    target_buy_limit_price,
)


def test_target_buy_limit_price_below_mid():
    assert target_buy_limit_price(1.10, 0.15) < 1.10


def test_stale_mid_passed_entry():
    reason = stale_pending_buy_reason(
        1.098,
        1.103,
        offset_pct=0.15,
        max_drift_pct=0.15,
        stale_enabled=True,
    )
    assert reason is not None
    assert "mid_passed_entry" in reason


def test_stale_kept_when_within_drift():
    mid = 1.103
    target = target_buy_limit_price(mid, 0.15)
    reason = stale_pending_buy_reason(
        target,
        mid,
        offset_pct=0.15,
        max_drift_pct=0.15,
        stale_enabled=True,
    )
    assert reason is None


def test_stale_snapshot_counts_cancel_candidates():
    snap = build_pending_buy_stale_snapshot(
        mid=1.103,
        operator_config={
            "alpha_buy_limit_offset_pct": 0.15,
            "alpha_stale_pending_buy_max_drift_pct": 0.15,
            "alpha_stale_pending_buy_enabled": True,
            "alpha_max_pending_buys": 1,
        },
        pending_records=[
            {"state": "pending_buy", "entry": 1.098, "bracket_id": "a"},
            {"state": "pending_buy", "entry": 1.1029, "bracket_id": "b"},
        ],
    )
    assert snap["would_cancel_count"] == 1
    assert snap["would_keep_count"] == 1
    assert snap["over_cap_count"] == 1


def test_build_skynet_context_includes_pending_buy_stale():
    ctx = build_skynet_context(
        {
            "mid": 1.103,
            "network": "mainnet",
            "brackets": {
                "summary": {"pending_buys": 2},
                "records": [
                    {"state": "pending_buy", "entry": 1.098, "bracket_id": "abcd"},
                ],
            },
        },
        operator_config={
            "alpha_stale_pending_buy_max_drift_pct": 0.15,
            "alpha_buy_limit_offset_pct": 0.15,
        },
    )
    assert "Pending buy stale diagnostics" in ctx
    assert '"would_cancel"' in ctx
