"""Tests for G3 intel JSONL + performance metrics."""

from __future__ import annotations

import json
from pathlib import Path

from experimental.ws_feed.intel_decisions_log import (
    append_intel_record,
    build_cycle_intel_record,
    build_peer_scrape_intel_record,
    tail_intel_records,
)
from experimental.ws_feed.performance_metrics import build_performance_metrics


def test_append_and_tail_intel_records(tmp_path: Path) -> None:
    path = tmp_path / "intel_decisions.jsonl"
    append_intel_record({"kind": "cycle", "cycle": 1}, path=path)
    append_intel_record({"kind": "peer_scrape", "peer_lane_count": 2}, path=path)
    rows = tail_intel_records(limit=10, path=path)
    assert len(rows) == 2
    assert rows[0]["kind"] == "cycle"
    assert rows[1]["peer_lane_count"] == 2


def test_build_cycle_intel_record_qd_flags() -> None:
    row = build_cycle_intel_record(
        cycle=5,
        mid=1.28,
        balance_xrp=50.0,
        balance_rlusd=200.0,
        portfolio_xrp=230.0,
        engine_dec={
            "qd_ask_allowed": False,
            "qd_bid_allowed": True,
            "inventory_label": "rlusd_heavy",
            "would_quote": True,
            "bid_size_xrp": 9.0,
            "ask_size_xrp": 0.0,
            "g2_grade": "neutral",
        },
        runtime_extras={"inventory_target_xrp_ratio": 0.55},
    )
    assert row["qd_ask_allowed"] is False
    assert row["qd_bid_allowed"] is True
    assert row["our_lane_xrp"] == 9.0
    assert row["xrp_ratio_pct"] is not None


def test_build_performance_metrics_from_trades(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    trades = logs / "trades_2026-06.csv"
    trades.write_text(
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
        "2026-06-15T12:00:00Z,BUY,yes,mainnet,BUY,10,0,1.28,0.08,,1,WS pure fill,,\n"
        "2026-06-15T12:01:00Z,SELL,yes,mainnet,SELL,10,0,1.28,0.06,,2,WS pure fill,,\n",
        encoding="utf-8",
    )
    intel = logs / "intel_decisions.jsonl"
    intel.write_text(
        json.dumps({"kind": "peer_scrape", "peer_lane_count": 1}) + "\n"
        + json.dumps({"kind": "peer_scrape", "peer_lane_count": 0}) + "\n",
        encoding="utf-8",
    )
    pm = build_performance_metrics(
        runtime={
            "inventory_xrp_ratio_pct": 42.0,
            "inventory_target_xrp_ratio": 0.55,
            "drawdown_pct": 3.0,
            "toxic_fill_ratio_30s": 0.1,
        },
        logs_dir=logs,
    )
    assert pm["capture"]["ws_fills"] == 2
    assert pm["capture"]["positive_capture_pct"] == 100.0
    assert len(pm["grades"]) == 5
    assert pm["peer_coverage_pct"] == 50.0
    assert pm["activation"]["tier"] in ("pilot", "pilot_watch", "warming_up", "active")


def test_build_peer_scrape_intel_record() -> None:
    row = build_peer_scrape_intel_record(
        {
            "our_lane_xrp": 8.0,
            "peer_lane_count": 3,
            "book_bid_offers": 20,
            "book_ask_offers": 10,
            "book_side_skew": 0.333,
            "book_side_skew_label": "bid_heavy",
        }
    )
    assert row["kind"] == "peer_scrape"
    assert row["peer_lane_count"] == 3
    assert row["book_side_skew_label"] == "bid_heavy"


def test_build_grok_suggestion_intel_record() -> None:
    from experimental.ws_feed.intel_decisions_log import build_grok_suggestion_intel_record

    row = build_grok_suggestion_intel_record(
        address="rTest",
        model="grok-3",
        briefing={
            "in_peer_lane": True,
            "source": "peer_lane",
            "touch_xrp": 9.0,
            "structured_briefing": {"schema_version": 1, "address": "rTest"},
        },
        result_text="Skim harder on asks when pressure is low.",
        context_snapshot={"competitor_pressure": 0.25, "inventory_label": "neutral"},
    )
    assert row["kind"] == "grok_suggestion"
    assert row["outcome_status"] == "pending"
    assert row["structured_briefing"]["schema_version"] == 1
    assert "Skim harder" in row["result_excerpt"]
