"""Tests for E1.5 WS-path session report."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.ws_path_session_report import (
    WS_FILL_MARKER,
    build_e15_report,
    session_spread_capture_xrp,
)


def test_e15_counts_ws_pure_fills(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    trades = logs / "trades_2026-06.csv"
    with trades.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "timestamp_utc",
                "event_type",
                "is_fill",
                "network",
                "side",
                "xrp_amount",
                "rlusd_amount",
                "price_rlusd_per_xrp",
                "profit_xrp_equiv",
                "cycle",
                "notes",
                "balance_xrp_after",
                "balance_rlusd_after",
            ]
        )
        w.writerow(
            [
                "2026-06-15T14:30:00",
                "BUY",
                "Y",
                "mainnet",
                "BUY",
                "9",
                "11",
                "1.23",
                "0.01",
                "1",
                f"{WS_FILL_MARKER} (balance delta)",
                "100",
                "100",
            ]
        )
    (logs / "runtime_state.json").write_text(
        '{"as_mode":"pure","dry_run":false,"fills_session":1,"toxic_fill_ratio":0.0}',
        encoding="utf-8",
    )
    report = build_e15_report(repo=tmp_path, min_fills=50)
    assert report.ws_fills == 1
    assert report.capture_xrp == 0.01
    assert not report.gate_fills_met


def test_session_spread_capture_uses_last_n_fills(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    trades = logs / "trades_2026-06.csv"
    with trades.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "timestamp_utc",
                "event_type",
                "side",
                "xrp_amount",
                "profit_xrp_equiv",
                "notes",
            ]
        )
        for i, cap in enumerate((0.01, 0.02, 0.03, 0.04)):
            w.writerow(
                [
                    f"2026-06-15T14:30:0{i}",
                    "BUY",
                    "BUY",
                    "1",
                    str(cap),
                    f"{WS_FILL_MARKER} @ mid 1.280000",
                ]
            )
    assert session_spread_capture_xrp(tmp_path, fills_session=2) == 0.07
    assert session_spread_capture_xrp(tmp_path, fills_session=0) == 0.0
