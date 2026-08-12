"""Tests for weekly Alpha Telegram report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.weekly_telegram_report import build_weekly_alpha_report


def test_weekly_report_narrative_stack(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_runtime_state.json").write_text(
        json.dumps(
            {
                "hud_kind": "alpha",
                "dry_run": False,
                "posture": "scale",
                "xrp": 500.0,
                "rlusd": 100.0,
                "mid": 1.0,
                "portfolio_xrp_equiv": 600.0,
                "inventory": {"label": "xrp_heavy", "deviation": 0.1, "target_xrp_ratio": 0.85},
                "risk": {"session_pnl_xrp": 50.0, "kill_switch_active": False},
                "decision": {"action": "hold", "reason": "balanced"},
                "reload_regime": {"phase": "funded", "deploy_floor_xrp_equiv": 40.0},
                "technical_analysis": {"bias": "neutral"},
            }
        ),
        encoding="utf-8",
    )
    (logs / "alpha_session.json").write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 400.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
                "baseline_xrp": 350.0,
                "baseline_rlusd": 50.0,
            }
        ),
        encoding="utf-8",
    )

    text = build_weekly_alpha_report(
        logs_dir=logs,
        now=datetime(2026, 6, 30, 9, 0, tzinfo=timezone.utc),
    )
    assert "Weekly stack chapter" in text
    assert "THE STACK" in text
    assert "Bot stack since baseline" in text
    assert "TOTAL BAG" in text
