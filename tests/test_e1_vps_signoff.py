"""Tests for E1 VPS ws-engine sign-off."""

from __future__ import annotations

import json
from pathlib import Path

from experimental.ws_feed.e1_vps_signoff import (
    E1SignoffCriteria,
    evaluate_e1_signoff,
    _would_quote_from_decisions,
)


def test_would_quote_from_dry_run_execution(tmp_path: Path) -> None:
    lines = [
        json.dumps(
            {
                "as_mode": "pure",
                "execution": "Dry-run: would sync 2 pure A-S quote(s).",
                "events": [],
            }
        ),
        json.dumps(
            {
                "as_mode": "pure",
                "execution": "Dry-run: no quotes (would_quote=false or empty intents).",
                "events": [],
            }
        ),
    ]
    stats = _would_quote_from_decisions(lines)
    assert stats["pure_decision_lines"] == 2
    assert stats["would_quote_lines"] == 1
    assert stats["would_quote_pct"] == 50.0


def test_e1_signoff_passes_good_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    rt = {
        "version": "2.0.0",
        "dry_run": True,
        "as_mode": "pure",
        "price_source": "ws_book_feed",
        "kill_switch_active": False,
        "cycle_count": 40,
        "ws_book_age_s": 2.5,
        "quote_decision_summary": "bid+ask inside",
        "quote_intents": [{"level": 1, "side": "bid", "active": True}],
        "as_reservation": 1.2,
        "as_optimal_spread_pct": 0.08,
        "market_edge_met": True,
        "inventory_label": "balanced",
    }
    (logs / "runtime_state.json").write_text(json.dumps(rt), encoding="utf-8")
    dec = logs / "decisions.jsonl"
    row = json.dumps(
        {
            "as_mode": "pure",
            "execution": "Dry-run: would sync 2 pure A-S quote(s).",
            "events": [],
        }
    )
    dec.write_text("\n".join([row] * 25) + "\n", encoding="utf-8")

    report = evaluate_e1_signoff(
        repo=tmp_path,
        criteria=E1SignoffCriteria(min_cycles=30, min_decision_lines=20),
        systemd_active=True,
    )
    assert report.passed
    assert report.ready_for_live_flip


def test_execution_summary_dry_run_would_sync() -> None:
    from config.settings import BotConfig
    from experimental.ws_feed.ws_pure_engine import WsPureTradingEngine

    engine = WsPureTradingEngine(BotConfig())
    engine.config.dry_run = True
    assert "would sync 2" in engine._execution_summary(engine.config, 0, would_sync=2)
