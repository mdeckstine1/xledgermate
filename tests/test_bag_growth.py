"""Tests for bag growth reporting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alpha.reporting.bag_growth import (
    build_bag_growth_snapshot,
    format_bag_growth_telegram_block,
)


def test_bag_growth_since_baseline_and_week(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)  # Tuesday
    (logs / "alpha_session.json").write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 400.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
                "last_portfolio_xrp": 500.0,
            }
        ),
        encoding="utf-8",
    )
    (logs / "alpha_bag_week.json").write_text(
        json.dumps(
            {
                "week_start_utc": "2026-06-29T00:00:00+00:00",
                "week_start_portfolio_xrp": 480.0,
            }
        ),
        encoding="utf-8",
    )

    snap = build_bag_growth_snapshot(
        xrp=500.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=now,
        persist_week=True,
    )

    assert snap["available"] is True
    assert snap["since_baseline_xrp"] == 100.0
    assert snap["week_delta_xrp"] == 20.0
    assert snap["portfolio_xrp_equiv"] == 500.0
    assert snap["portfolio_rlusd_equiv"] == 500.0
    assert snap["high_water_portfolio_xrp"] == 500.0

    block = format_bag_growth_telegram_block(snap)
    assert "TOTAL BAG" in block
    assert "This week" in block


def test_bag_growth_rolls_week_on_monday(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_session.json").write_text(
        json.dumps({"baseline_portfolio_xrp": 100.0, "baseline_utc": "2026-06-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    old_week = datetime(2026, 6, 28, 23, 0, tzinfo=timezone.utc)  # Sunday
    new_week = datetime(2026, 6, 29, 1, 0, tzinfo=timezone.utc)  # Monday

    build_bag_growth_snapshot(
        xrp=110.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=old_week,
        persist_week=True,
    )
    snap = build_bag_growth_snapshot(
        xrp=120.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=new_week,
        persist_week=True,
    )

    week_data = json.loads((logs / "alpha_bag_week.json").read_text(encoding="utf-8"))
    assert week_data["week_start_portfolio_xrp"] == 120.0
    assert snap["week_delta_xrp"] == 0.0


def test_bag_growth_xrp_stack_delta(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
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

    snap = build_bag_growth_snapshot(
        xrp=380.0,
        rlusd=40.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        persist_week=False,
    )
    assert snap["xrp_stack_delta_raw"] == 30.0
    assert snap["xrp_stack_delta_bot"] == 30.0


def test_bag_scoreboard_day_and_high_water(tmp_path: Path) -> None:
    """TOTAL BAG day Δ + lifetime ATH track whether ~portfolio is climbing."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_session.json").write_text(
        json.dumps(
            {
                "baseline_portfolio_xrp": 1000.0,
                "baseline_utc": "2026-06-22T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    morning = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
    afternoon = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
    next_day = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)

    s1 = build_bag_growth_snapshot(
        xrp=1140.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=morning,
        persist_week=True,
    )
    assert s1["portfolio_xrp_equiv"] == 1140.0
    assert s1["day_delta_xrp"] == 0.0
    assert s1["at_high_water"] is True
    assert s1["high_water_portfolio_xrp"] == 1140.0

    s2 = build_bag_growth_snapshot(
        xrp=1145.1,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=afternoon,
        persist_week=True,
    )
    assert s2["portfolio_xrp_equiv"] == 1145.1
    assert s2["day_delta_xrp"] == 5.1
    assert s2["at_high_water"] is True
    assert s2["high_water_portfolio_xrp"] == 1145.1

    s3 = build_bag_growth_snapshot(
        xrp=1142.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=afternoon.replace(hour=18),
        persist_week=True,
    )
    assert s3["off_high_xrp"] == -3.1
    assert s3["at_high_water"] is False
    assert s3["high_water_portfolio_xrp"] == 1145.1

    s4 = build_bag_growth_snapshot(
        xrp=1143.0,
        rlusd=0.0,
        mid_rlusd_per_xrp=1.0,
        logs_dir=logs,
        now=next_day,
        persist_week=True,
    )
    assert s4["day_delta_xrp"] == 0.0  # new day anchors at open
    assert s4["high_water_portfolio_xrp"] == 1145.1  # ATH persists across days

    block = format_bag_growth_telegram_block(s2)
    assert "TOTAL BAG" in block
    assert "1145.1000" in block
