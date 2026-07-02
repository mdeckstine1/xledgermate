"""Tests for HUD live metric refresh on /state poll."""

from __future__ import annotations

import json
from pathlib import Path

from alpha.hud.state_export import refresh_live_metrics_in_state
from alpha.reporting.operator_deposits import record_deposit


def test_refresh_live_metrics_applies_deposits(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_session.json").write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 400.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
                "last_portfolio_xrp": 600.0,
            }
        ),
        encoding="utf-8",
    )
    record_deposit(
        xrp=100.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        reset_session_baseline=False,
    )

    stale = {
        "xrp": 600.0,
        "rlusd": 0.0,
        "mid": 1.0,
        "bag_growth": {
            "since_baseline_xrp": 200.0,
            "operator_deposits_xrp_equiv": 0.0,
        },
        "risk": {"session_pnl_xrp": 200.0},
    }
    out = refresh_live_metrics_in_state(stale, logs_dir=logs)
    bag = out["bag_growth"]
    assert bag["operator_deposits_xrp_equiv"] == 100.0
    assert bag["since_baseline_bot_xrp"] == 100.0
    assert out["risk"]["session_pnl_xrp"] == 200.0
