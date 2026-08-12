"""Tests for Alpha Telegram narrative reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alpha.reporting.telegram_narrative import (
    build_alpha_narrative_report,
    build_recommendations,
)


def _state(**over):
    base = {
        "hud_kind": "alpha",
        "dry_run": False,
        "posture": "scale",
        "xrp": 1000.0,
        "rlusd": 100.0,
        "mid": 1.0,
        "portfolio_xrp_equiv": 1100.0,
        "inventory": {"label": "xrp_heavy", "deviation": 0.08, "target_xrp_ratio": 0.85},
        "risk": {"session_pnl_xrp": 10.0, "kill_switch_active": False, "drawdown_pct": 1.0},
        "decision": {"action": "hold", "reason": "balanced dev=+0.01"},
        "reload_regime": {"phase": "funded", "blocks_accumulation": False, "deploy_floor_xrp_equiv": 40.0},
        "accumulation_regime": {
            "harvest_watch": {"phase": "idle", "rolling": {"move_pct": -0.5}},
            "dip_deploy_watch": {"phase": "idle", "rolling": {"move_pct": -0.5}},
        },
        "technical_analysis": {"bias": "neutral", "buy_score": 1.5, "sell_score": 1.5},
        "open_offers": [],
    }
    base.update(over)
    return base


def _logs_with_session(tmp_path: Path) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_session.json").write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 1000.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
                "baseline_xrp": 900.0,
                "baseline_rlusd": 100.0,
            }
        ),
        encoding="utf-8",
    )
    (logs / "alpha_bag_week.json").write_text(
        json.dumps(
            {
                "week_start_utc": "2026-08-10T00:00:00+00:00",
                "week_start_portfolio_xrp": 1090.0,
                "week_start_xrp": 990.0,
                "day_start_utc": "2026-08-12T00:00:00+00:00",
                "day_start_portfolio_xrp": 1095.0,
                "high_water_portfolio_xrp": 1110.0,
            }
        ),
        encoding="utf-8",
    )
    return logs


def test_daily_narrative_has_stack_sections(tmp_path: Path) -> None:
    logs = _logs_with_session(tmp_path)
    text = build_alpha_narrative_report(
        state=_state(),
        logs_dir=logs,
        period="daily",
        now=datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc),
    )
    assert "Daily bag story" in text
    assert "THE STACK" in text
    assert "Bot stack since baseline" in text
    assert "THE MARKET" in text
    assert "THE BOT" in text
    assert "TOTAL BAG" in text
    assert "BOT ADDED" in text
    assert "RECOMMENDATIONS" in text


def test_pulse_is_short_and_stack_first(tmp_path: Path) -> None:
    logs = _logs_with_session(tmp_path)
    text = build_alpha_narrative_report(
        state=_state(),
        logs_dir=logs,
        period="pulse",
        now=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
    )
    assert "Hourly pulse" in text
    assert "STACK" in text
    assert "QD" not in text
    assert "Session P&L" not in text
    assert len(text.splitlines()) < 20


def test_weekly_chapter(tmp_path: Path) -> None:
    logs = _logs_with_session(tmp_path)
    text = build_alpha_narrative_report(
        state=_state(),
        logs_dir=logs,
        period="weekly",
        now=datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc),
        persist_week=False,
    )
    assert "Weekly stack chapter" in text
    assert "THE WEEK" in text


def test_recs_on_sell_slot_stall(tmp_path: Path) -> None:
    logs = _logs_with_session(tmp_path)
    state = _state(decision={"action": "hold", "reason": "max_pending_sells=2"})
    text = build_alpha_narrative_report(
        state=state,
        logs_dir=logs,
        period="daily",
        now=datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc),
    )
    assert "Sell slots full" in text or "stale" in text.lower()


def test_build_recommendations_empty_when_healthy() -> None:
    bag = {
        "at_high_water": True,
        "off_high_xrp": 0.0,
        "operator_deposits_xrp_equiv": 0.0,
    }
    state = _state()
    recs = build_recommendations(state, bag, agent={})
    assert recs == []
