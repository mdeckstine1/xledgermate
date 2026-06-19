"""Tests for G6 live activation grading."""

from __future__ import annotations

import json
from pathlib import Path

from experimental.ws_feed.live_activation_grading import (
    G6Criteria,
    build_g6_report,
    resolve_activation_tier,
    summarize_activation,
)


def _grades(capture: str = "good", tox: str = "good", inv: str = "good", dd: str = "good"):
    return [
        {"id": "spread_capture", "label": "Spread capture", "grade": capture, "value": "ok"},
        {"id": "toxicity", "label": "Toxicity", "grade": tox, "value": "ok"},
        {"id": "inventory_health", "label": "Inventory", "grade": inv, "value": "ok"},
        {"id": "drawdown", "label": "Drawdown", "grade": dd, "value": "ok"},
        {"id": "peer_lane", "label": "Peer lane", "grade": "neutral", "value": "ok"},
    ]


def test_resolve_activation_tier_warming_up() -> None:
    tier, _ = resolve_activation_tier(
        grades=_grades(),
        n_fills=3,
        runtime={"dry_run": False},
        criteria=G6Criteria(),
    )
    assert tier == "warming_up"


def test_resolve_activation_tier_hold_on_bad_capture() -> None:
    tier, summary = resolve_activation_tier(
        grades=_grades(capture="attention"),
        n_fills=12,
        runtime={"dry_run": False},
        criteria=G6Criteria(),
    )
    assert tier == "hold"
    assert "capture" in summary.lower()


def test_summarize_activation_hold_includes_attention_on() -> None:
    block = summarize_activation(
        runtime={"dry_run": False},
        performance_metrics={
            "grades": _grades(capture="attention"),
            "capture": {"ws_fills": 12},
        },
    )
    assert block["tier"] == "hold"
    assert block["gate_pass"] is False
    assert "Spread capture" in block["attention_on"]


def test_resolve_activation_tier_active() -> None:
    tier, _ = resolve_activation_tier(
        grades=_grades(),
        n_fills=30,
        runtime={"dry_run": False},
        criteria=G6Criteria(),
    )
    assert tier == "active"


def test_resolve_activation_tier_scale_ready() -> None:
    tier, _ = resolve_activation_tier(
        grades=_grades(),
        n_fills=55,
        runtime={"dry_run": False},
        criteria=G6Criteria(),
    )
    assert tier == "scale_ready"


def test_summarize_activation_includes_tier() -> None:
    block = summarize_activation(
        runtime={"dry_run": False},
        performance_metrics={"grades": _grades(), "capture": {"ws_fills": 30}},
    )
    assert block["tier"] == "active"
    assert block["ws_fills"] == 30


def test_build_g6_report_from_logs(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    trades = logs / "trades_2026-06.csv"
    trades.write_text(
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
        + "\n".join(
            f"2026-06-15T12:{i:02d}:00Z,BUY,yes,mainnet,BUY,10,0,1.28,0.08,,{i},WS pure fill,,"
            for i in range(10)
        )
        + "\n",
        encoding="utf-8",
    )
    intel = logs / "intel_decisions.jsonl"
    intel.write_text(
        "\n".join(
            json.dumps(
                {
                    "kind": "cycle",
                    "g2_active": i % 3 == 0,
                    "g4_active": i % 5 == 0,
                    "g2_grade": "neutral",
                    "g4_grade": "neutral",
                    "would_quote": True,
                }
            )
            for i in range(20)
        )
        + "\n",
        encoding="utf-8",
    )
    runtime = logs / "runtime_state.json"
    runtime.write_text(
        json.dumps(
            {
                "dry_run": False,
                "kill_switch_active": False,
                "portfolio_value_xrp": 240.0,
                "session_baseline_portfolio_xrp": 234.0,
                "session_pnl_balance_xrp": 0.12,
                "inventory_xrp_ratio_pct": 52.0,
                "inventory_target_xrp_ratio": 0.55,
                "drawdown_pct": 2.0,
                "toxic_fill_ratio_30s": 0.1,
            }
        ),
        encoding="utf-8",
    )
    report = build_g6_report(runtime_path=runtime, logs_dir=logs)
    assert report.structural_signals["cycle_rows"] == 20
    assert report.portfolio["portfolio_xrp_equiv"] == 240.0
    assert report.performance_metrics["capture"]["ws_fills"] == 10
    assert report.activation_tier in ("pilot", "pilot_watch", "hold", "active")
