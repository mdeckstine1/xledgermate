"""Tests for weekly Alpha Telegram report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.weekly_telegram_report import build_weekly_alpha_report


def test_weekly_report_includes_bag_block(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_runtime_state.json").write_text(
        json.dumps(
            {
                "dry_run": False,
                "posture": "patient",
                "xrp": 500.0,
                "rlusd": 100.0,
                "mid": 1.0,
                "portfolio_xrp_equiv": 600.0,
                "inventory": {"label": "xrp_heavy", "deviation": 0.1},
                "risk": {"session_pnl_xrp": 50.0},
                "decision": {"action": "HOLD", "reason": "buy_block"},
            }
        ),
        encoding="utf-8",
    )
    (logs / "alpha_session.json").write_text(
        json.dumps({"baseline_portfolio_xrp": 400.0, "baseline_utc": "2026-06-22T00:00:00+00:00"}),
        encoding="utf-8",
    )

    text = build_weekly_alpha_report(
        logs_dir=logs,
        now=datetime(2026, 6, 30, 9, 0, tzinfo=timezone.utc),
    )
    assert "weekly bag report" in text
    assert "Bag growth" in text
    assert "Since baseline" in text
