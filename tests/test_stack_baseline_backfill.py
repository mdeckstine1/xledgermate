"""Tests for tax CSV stack baseline backfill."""

from __future__ import annotations

import csv
from pathlib import Path

from alpha.reporting.bag_growth import _stack_baseline_from_tax_csv


def test_stack_baseline_skips_zero_balance_rows(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "trades_2026-06.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "timestamp_utc",
                "event_type",
                "taxable",
                "network",
                "side",
                "xrp_amount",
                "rlusd_amount",
                "price_rlusd_per_xrp",
                "profit_xrp_equiv",
                "tx_hash",
                "cycle",
                "notes",
                "balance_xrp_after",
                "balance_rlusd_after",
            ]
        )
        w.writerow(
            [
                "2026-06-21T20:20:22+00:00",
                "BUY",
                "Y",
                "mainnet",
                "BUY",
                "1",
                "1",
                "1",
                "0",
                "",
                "1",
                "note",
                "229.07",
                "166.17",
            ]
        )
        w.writerow(
            [
                "2026-06-21T20:21:08+00:00",
                "OFFER",
                "N",
                "mainnet",
                "",
                "0",
                "0",
                "0",
                "0",
                "",
                "1",
                "refresh",
                "0",
                "0",
            ]
        )

    xrp, rlusd = _stack_baseline_from_tax_csv(logs, "2026-06-22T14:48:49+00:00")
    assert xrp == 229.07
    assert rlusd == 166.17
