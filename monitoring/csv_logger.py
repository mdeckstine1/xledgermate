"""Monthly CSV for trades, major events, and tax-relevant activity."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class CSVLogger:
    """
    Append-only monthly file: logs/trades_YYYY-MM.csv

    Event types:
      BUY, SELL     — inferred or confirmed fills (taxable)
      TRANSFER      — outbound/inbound payments (taxable)
      MAJOR         — kill switch, engine milestones, errors (not taxable)
      OFFER_REFRESH — live cancel/replace cycle (not taxable)
    """

    HEADER = [
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

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self._month_key = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        self.filepath = self.log_dir / f"trades_{self._month_key}.csv"
        self._ensure_header()

    def _ensure_header(self) -> None:
        month_key = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        if month_key != self._month_key:
            self._month_key = month_key
            self.filepath = self.log_dir / f"trades_{month_key}.csv"
        if not self.filepath.exists():
            with self.filepath.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(self.HEADER)

    def log_event(
        self,
        *,
        event_type: str,
        taxable: bool,
        network: str = "",
        side: str = "",
        xrp_amount: float = 0.0,
        rlusd_amount: float = 0.0,
        price_rlusd_per_xrp: float = 0.0,
        profit_xrp_equiv: float = 0.0,
        tx_hash: str = "",
        cycle: int = 0,
        notes: str = "",
        balance_xrp_after: float = 0.0,
        balance_rlusd_after: float = 0.0,
    ) -> None:
        self._ensure_header()
        with self.filepath.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(
                [
                    datetime.now(tz=timezone.utc).isoformat(),
                    event_type.upper(),
                    "Y" if taxable else "N",
                    network,
                    side.upper() if side else "",
                    f"{xrp_amount:.6f}",
                    f"{rlusd_amount:.6f}",
                    f"{price_rlusd_per_xrp:.6f}",
                    f"{profit_xrp_equiv:.6f}",
                    tx_hash,
                    cycle,
                    notes,
                    f"{balance_xrp_after:.6f}",
                    f"{balance_rlusd_after:.6f}",
                ]
            )

    def log_buy(
        self,
        *,
        network: str,
        xrp_amount: float,
        rlusd_amount: float,
        price_rlusd_per_xrp: float,
        cycle: int = 0,
        notes: str = "",
        tx_hash: str = "",
        balance_xrp_after: float = 0.0,
        balance_rlusd_after: float = 0.0,
    ) -> None:
        self.log_event(
            event_type="BUY",
            taxable=True,
            network=network,
            side="BUY",
            xrp_amount=xrp_amount,
            rlusd_amount=rlusd_amount,
            price_rlusd_per_xrp=price_rlusd_per_xrp,
            cycle=cycle,
            notes=notes,
            tx_hash=tx_hash,
            balance_xrp_after=balance_xrp_after,
            balance_rlusd_after=balance_rlusd_after,
        )

    def log_sell(
        self,
        *,
        network: str,
        xrp_amount: float,
        rlusd_amount: float,
        price_rlusd_per_xrp: float,
        cycle: int = 0,
        notes: str = "",
        tx_hash: str = "",
        balance_xrp_after: float = 0.0,
        balance_rlusd_after: float = 0.0,
    ) -> None:
        self.log_event(
            event_type="SELL",
            taxable=True,
            network=network,
            side="SELL",
            xrp_amount=xrp_amount,
            rlusd_amount=rlusd_amount,
            price_rlusd_per_xrp=price_rlusd_per_xrp,
            cycle=cycle,
            notes=notes,
            tx_hash=tx_hash,
            balance_xrp_after=balance_xrp_after,
            balance_rlusd_after=balance_rlusd_after,
        )

    def log_transfer(
        self,
        *,
        network: str,
        asset: str,
        amount: float,
        destination: str,
        tx_hash: str,
        balance_xrp_after: float = 0.0,
        balance_rlusd_after: float = 0.0,
    ) -> None:
        xrp_amt = amount if asset.upper() == "XRP" else 0.0
        rlusd_amt = amount if asset.upper() == "RLUSD" else 0.0
        self.log_event(
            event_type="TRANSFER",
            taxable=True,
            network=network,
            side="OUT",
            xrp_amount=xrp_amt,
            rlusd_amount=rlusd_amt,
            tx_hash=tx_hash,
            notes=f"Payment to {destination}",
            balance_xrp_after=balance_xrp_after,
            balance_rlusd_after=balance_rlusd_after,
        )

    def log_major(
        self,
        *,
        network: str,
        notes: str,
        cycle: int = 0,
        tx_hash: str = "",
    ) -> None:
        self.log_event(
            event_type="MAJOR",
            taxable=False,
            network=network,
            cycle=cycle,
            notes=notes,
            tx_hash=tx_hash,
        )

    def log_offer_refresh(
        self,
        *,
        network: str,
        placed: int,
        cancelled: int,
        cycle: int,
        dry_run: bool,
    ) -> None:
        mode = "dry-run" if dry_run else "live"
        self.log_event(
            event_type="OFFER_REFRESH",
            taxable=False,
            network=network,
            cycle=cycle,
            notes=f"{mode}: cancelled {cancelled}, placed {placed} offer(s)",
        )

    # Backward-compatible alias
    def log_trade(
        self,
        event: str,
        xrp_amount: float,
        rlusd_amount: float,
        price: float,
        profit_xrp: float,
        balance_after: float,
    ) -> None:
        side = event.upper()
        if side in ("BUY", "SELL"):
            kwargs = dict(
                network="",
                xrp_amount=xrp_amount,
                rlusd_amount=rlusd_amount,
                price_rlusd_per_xrp=price,
                balance_xrp_after=balance_after,
            )
            if side == "BUY":
                self.log_buy(**kwargs)
            else:
                self.log_sell(**kwargs)
        else:
            self.log_major(network="", notes=event)
