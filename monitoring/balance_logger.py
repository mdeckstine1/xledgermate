"""Append portfolio snapshots each engine cycle."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path


class BalanceLogger:
    def __init__(self, log_dir: str = "logs") -> None:
        self.path = Path(log_dir) / "portfolio_snapshots.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header()

    def _ensure_header(self) -> None:
        if self.path.exists():
            return
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp_utc",
                    "cycle",
                    "network",
                    "xrp_balance",
                    "rlusd_balance",
                    "mid_rlusd_per_xrp",
                    "portfolio_xrp_equiv",
                    "open_offers",
                    "dry_run",
                ]
            )

    def log_snapshot(
        self,
        *,
        cycle: int,
        network: str,
        xrp_balance: float,
        rlusd_balance: float,
        mid_rlusd_per_xrp: float,
        portfolio_xrp_equiv: float,
        open_offers: int,
        dry_run: bool,
    ) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    datetime.now(tz=timezone.utc).isoformat(),
                    cycle,
                    network,
                    f"{xrp_balance:.6f}",
                    f"{rlusd_balance:.6f}",
                    f"{mid_rlusd_per_xrp:.6f}",
                    f"{portfolio_xrp_equiv:.6f}",
                    open_offers,
                    dry_run,
                ]
            )
