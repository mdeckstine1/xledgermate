"""Acquisition metrics — edge-positive inventory growth vs spot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from experimental.ws_feed.acquisition_context import (
    extract_acquisition_fill_context,
    solo_acquire_bid_join_fired,
    solo_acquire_opportunity,
)
from experimental.ws_feed.acquisition_metrics import (
    build_acquisition_metrics,
    format_acquisition_report,
)
from experimental.ws_feed.intel_decisions_log import build_cycle_intel_record


def test_solo_acquire_opportunity_requires_empty_peer_low_toxic() -> None:
    assert solo_acquire_opportunity(
        peer_lane_empty=True,
        toxic_ratio_30s=0.1,
        g2_spread_mult=1.0,
    )
    assert not solo_acquire_opportunity(
        peer_lane_empty=False,
        toxic_ratio_30s=0.1,
        g2_spread_mult=1.0,
    )
    assert not solo_acquire_opportunity(
        peer_lane_empty=True,
        toxic_ratio_30s=0.25,
        g2_spread_mult=1.0,
    )


def test_solo_acquire_bid_join_fired() -> None:
    assert solo_acquire_bid_join_fired(g7_solo_acquisition=True, g7_bid_role="join")
    assert not solo_acquire_bid_join_fired(g7_solo_acquisition=True, g7_bid_role="backoff")
    assert not solo_acquire_bid_join_fired(g7_solo_acquisition=False, g7_bid_role="join")


def test_extract_acquisition_fill_context() -> None:
    ctx = extract_acquisition_fill_context(
        {
            "inventory_label": "balanced",
            "g7_solo_acquisition": True,
            "g7_bid_role": "join",
            "g2_spread_mult": 1.0,
        },
        competitor_intel={"peer_lane_empty": True, "peer_lane_count": 0},
    )
    assert ctx["inventory_label"] == "balanced"
    assert ctx["g7_solo_acquisition"] is True
    assert ctx["peer_lane_empty"] is True


def test_build_acquisition_metrics_buy_and_solo_fire_rate() -> None:
    runtime = {
        "mid_price": 1.15,
        "balance_xrp": 190.0,
        "balance_rlusd": 200.0,
        "session_baseline_xrp": 188.0,
        "session_baseline_rlusd": 200.0,
        "session_baseline_mid": 1.15,
        "session_spread_capture_xrp": 0.05,
    }
    fills = [
        {
            "side": "BUY",
            "xrp_amount": 10.0,
            "capture_xrp": 0.08,
            "inventory_label": "balanced",
            "fill_price_rlusd_per_xrp": 1.148,
        },
        {
            "side": "SELL",
            "xrp_amount": 8.0,
            "capture_xrp": -0.04,
            "inventory_label": "xrp_heavy",
        },
    ]
    intel = [
        {
            "kind": "cycle",
            "peer_lane_empty": True,
            "toxic_fill_ratio_30s": 0.1,
            "g2_spread_mult": 1.0,
            "would_quote": True,
            "g7_solo_acquisition": True,
            "g7_bid_role": "join",
            "inventory_label": "balanced",
            "worst_vs_touch_bps": 6.0,
        },
        {
            "kind": "cycle",
            "peer_lane_empty": True,
            "toxic_fill_ratio_30s": 0.1,
            "g2_spread_mult": 1.0,
            "would_quote": True,
            "g7_solo_acquisition": False,
            "inventory_label": "balanced",
        },
    ]
    m = build_acquisition_metrics(runtime=runtime, session_fills=fills, intel_cycles=intel)
    assert m["xrp_per_rlusd_spent"] is not None
    assert m["buy_cost_vs_mid_bps"] is not None
    assert m["solo_acquire_fire_rate"] == 0.5
    assert m["bid_join_fire_rate"] == 0.5
    assert m["inventory_growth_at_edge"]["at_edge"] is True
    assert "balanced" in m["buy_capture_by_state"]


def test_build_cycle_intel_record_acquisition_fields() -> None:
    row = build_cycle_intel_record(
        cycle=3,
        mid=1.28,
        balance_xrp=50.0,
        balance_rlusd=200.0,
        portfolio_xrp=230.0,
        engine_dec={
            "g7_solo_acquisition": True,
            "g7_bid_role": "join",
            "g7_ask_sell_defense": False,
        },
        runtime_extras={
            "peer_lane_empty": True,
            "worst_vs_touch_bps": 12.5,
        },
    )
    assert row["g7_solo_acquisition"] is True
    assert row["peer_lane_empty"] is True
    assert row["worst_vs_touch_bps"] == 12.5


def test_hud_market_payload_includes_solo_acquisition_fields() -> None:
    from experimental.ws_feed.live_pure_as_tester import _hud_market_payload

    payload = _hud_market_payload(
        {
            "mid_price": 1.15,
            "g7_solo_acquisition": True,
            "peer_lane_empty": True,
            "g4_grade": "solo_acquire",
            "g7_scaler_label": "bid join 5.0bps · ask join 5.0bps",
        },
        ws_as_version="2.1.31",
    )
    assert payload["g7_solo_acquisition"] is True
    assert payload["peer_lane_empty"] is True
    assert payload["g4_grade"] == "solo_acquire"

    metrics = {
        "xrp_per_rlusd_spent": 0.87,
        "buy_cost_vs_mid_bps": 4.2,
        "solo_acquire_fire_rate": 0.75,
        "solo_acquire_fired_cycles": 3,
        "solo_acquire_opportunities": 4,
        "inventory_growth_at_edge": {"delta_xrp": 1.5, "buy_capture_xrp": 0.1, "at_edge": True},
        "buy_capture_by_state": {"balanced": {"n": 2.0, "cap": 0.1, "xrp": 20.0}},
        "sell_capture_by_state": {},
    }
    text = format_acquisition_report(metrics, runtime={"ws_as_version": "2.1.28", "fills_session": 2})
    assert "Acquisition metrics" in text
    assert "solo_acquire_fire_rate" in text


def test_acquisition_metrics_report_script(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    runtime = {
        "mid_price": 1.15,
        "balance_xrp": 189.0,
        "balance_rlusd": 200.0,
        "session_baseline_xrp": 188.0,
        "session_baseline_rlusd": 200.0,
        "session_baseline_mid": 1.15,
        "session_spread_capture_xrp": 0.02,
        "session_boot_utc": "2026-06-20T07:35:08+00:00",
        "ws_as_version": "2.1.28",
        "fills_session": 1,
    }
    (logs / "runtime_state.json").write_text(json.dumps(runtime), encoding="utf-8")
    fill_row = {
        "kind": "fill",
        "ts_utc": "2026-06-20T08:00:00+00:00",
        "side": "BUY",
        "xrp_amount": 5.0,
        "capture_xrp": 0.03,
        "inventory_label": "balanced",
        "fill_price_rlusd_per_xrp": 1.148,
        "ws_as_version": "2.1.28",
    }
    (logs / "fill_quote_age.jsonl").write_text(json.dumps(fill_row) + "\n", encoding="utf-8")
    intel_row = {
        "kind": "cycle",
        "ts_utc": "2026-06-20T08:01:00+00:00",
        "peer_lane_empty": True,
        "toxic_fill_ratio_30s": 0.05,
        "g2_spread_mult": 1.0,
        "would_quote": True,
        "g7_solo_acquisition": True,
        "g7_bid_role": "join",
        "inventory_label": "balanced",
        "ws_as_version": "2.1.28",
    }
    (logs / "intel_decisions.jsonl").write_text(json.dumps(intel_row) + "\n", encoding="utf-8")

    from scripts.acquisition_metrics_report import build_acquisition_report, format_acquisition_report_cli

    report = build_acquisition_report(logs_dir=logs)
    assert report.fills_count == 1
    assert report.metrics["buy_cost_vs_mid_bps"] is not None
    text = format_acquisition_report_cli(report)
    assert "Acquisition metrics" in text
