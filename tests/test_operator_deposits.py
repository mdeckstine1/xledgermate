"""Tests for operator deposit ledger."""

from __future__ import annotations

import json
from pathlib import Path

from alpha.reporting.bag_growth import build_bag_growth_snapshot
from alpha.reporting.operator_deposits import (
    delete_deposit,
    deposits_snapshot,
    record_deposit,
    total_deposits_xrp_equiv,
)


def test_record_deposit_and_bag_growth_adjustment(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_session.json").write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 400.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
                "last_portfolio_xrp": 550.0,
            }
        ),
        encoding="utf-8",
    )

    entry, errors = record_deposit(
        xrp=100.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        note="tranche add",
        logs_dir=logs,
        reset_session_baseline=False,
    )
    assert not errors
    assert entry["xrp_equiv"] == 100.0
    assert total_deposits_xrp_equiv(logs) == 100.0

    snap = build_bag_growth_snapshot(
        xrp=550.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        persist_week=False,
    )
    assert snap["since_baseline_xrp"] == 150.0
    assert snap["operator_deposits_xrp_equiv"] == 100.0
    assert snap["since_baseline_bot_xrp"] == 50.0


def test_delete_deposit(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    entry, _ = record_deposit(
        xrp=10.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
    )
    assert deposits_snapshot(logs)["count"] == 1
    assert delete_deposit(entry["id"], logs_dir=logs)
    assert deposits_snapshot(logs)["count"] == 0
    assert total_deposits_xrp_equiv(logs) == 0.0


def test_record_deposit_resets_session_baseline(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    session = logs / "alpha_session.json"
    session.write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 400.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
                "last_portfolio_xrp": 500.0,
            }
        ),
        encoding="utf-8",
    )
    entry, errors = record_deposit(
        xrp=50.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        reset_session_baseline=True,
    )
    assert entry["session_baseline_reset"] is True
    data = json.loads(session.read_text(encoding="utf-8"))
    assert data["baseline_portfolio_xrp"] == 500.0
