"""Monthly CSV for trades, major events, and tax-relevant activity."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


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
        "cost_basis_rlusd_per_xrp",
        "proceeds_usd",
    ]

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self._month_key = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        self.filepath = self.log_dir / f"trades_{self._month_key}.csv"
        self._ensure_header()

    def _read_header(self, path: Path) -> List[str]:
        if not path.is_file():
            return list(self.HEADER)
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.reader(handle), None)
            return list(row) if row else list(self.HEADER)
        except OSError:
            return list(self.HEADER)

    def _upgrade_header_if_needed(self, path: Path) -> None:
        header = self._read_header(path)
        if header == self.HEADER:
            return
        if not path.is_file():
            return
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                old_rows = list(reader)
        except OSError:
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.HEADER, extrasaction="ignore")
            writer.writeheader()
            for row in old_rows:
                writer.writerow({key: row.get(key, "") for key in self.HEADER})

    def _ensure_header(self) -> None:
        month_key = datetime.now(tz=timezone.utc).strftime("%Y-%m")
        if month_key != self._month_key:
            self._month_key = month_key
            self.filepath = self.log_dir / f"trades_{month_key}.csv"
        if not self.filepath.exists():
            with self.filepath.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(self.HEADER)
        else:
            self._upgrade_header_if_needed(self.filepath)

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
        cost_basis_rlusd_per_xrp: Optional[float] = None,
        proceeds_usd: Optional[float] = None,
    ) -> None:
        self._ensure_header()
        row = {
            "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
            "event_type": event_type.upper(),
            "taxable": "Y" if taxable else "N",
            "network": network,
            "side": side.upper() if side else "",
            "xrp_amount": f"{xrp_amount:.6f}",
            "rlusd_amount": f"{rlusd_amount:.6f}",
            "price_rlusd_per_xrp": f"{price_rlusd_per_xrp:.6f}",
            "profit_xrp_equiv": f"{profit_xrp_equiv:.6f}",
            "tx_hash": tx_hash,
            "cycle": cycle,
            "notes": notes,
            "balance_xrp_after": f"{balance_xrp_after:.6f}",
            "balance_rlusd_after": f"{balance_rlusd_after:.6f}",
            "cost_basis_rlusd_per_xrp": (
                f"{float(cost_basis_rlusd_per_xrp):.6f}" if cost_basis_rlusd_per_xrp is not None else ""
            ),
            "proceeds_usd": f"{float(proceeds_usd):.4f}" if proceeds_usd is not None else "",
        }
        with self.filepath.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.HEADER, extrasaction="ignore")
            writer.writerow(row)

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
        profit_xrp_equiv: float = 0.0,
        balance_xrp_after: float = 0.0,
        balance_rlusd_after: float = 0.0,
        cost_basis_rlusd_per_xrp: Optional[float] = None,
    ) -> None:
        basis = price_rlusd_per_xrp if cost_basis_rlusd_per_xrp is None else cost_basis_rlusd_per_xrp
        self.log_event(
            event_type="BUY",
            taxable=True,
            network=network,
            side="BUY",
            xrp_amount=xrp_amount,
            rlusd_amount=rlusd_amount,
            price_rlusd_per_xrp=price_rlusd_per_xrp,
            profit_xrp_equiv=profit_xrp_equiv,
            cycle=cycle,
            notes=notes,
            tx_hash=tx_hash,
            balance_xrp_after=balance_xrp_after,
            balance_rlusd_after=balance_rlusd_after,
            cost_basis_rlusd_per_xrp=basis,
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
        profit_xrp_equiv: float = 0.0,
        balance_xrp_after: float = 0.0,
        balance_rlusd_after: float = 0.0,
        cost_basis_rlusd_per_xrp: Optional[float] = None,
        proceeds_usd: Optional[float] = None,
    ) -> None:
        self.log_event(
            event_type="SELL",
            taxable=True,
            network=network,
            side="SELL",
            xrp_amount=xrp_amount,
            rlusd_amount=rlusd_amount,
            price_rlusd_per_xrp=price_rlusd_per_xrp,
            profit_xrp_equiv=profit_xrp_equiv,
            cycle=cycle,
            notes=notes,
            tx_hash=tx_hash,
            balance_xrp_after=balance_xrp_after,
            balance_rlusd_after=balance_rlusd_after,
            cost_basis_rlusd_per_xrp=cost_basis_rlusd_per_xrp,
            proceeds_usd=proceeds_usd,
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
        proceeds_usd: Optional[float] = None,
    ) -> None:
        xrp_amt = amount if asset.upper() == "XRP" else 0.0
        rlusd_amt = amount if asset.upper() == "RLUSD" else 0.0
        usd = proceeds_usd
        if usd is None and rlusd_amt > 0:
            usd = rlusd_amt
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
            proceeds_usd=usd,
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
