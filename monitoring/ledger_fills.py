"""Ledger-accurate fill detection via account_tx balance deltas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


MIN_RLUSD_DELTA = 0.0001
MIN_XRP_DELTA = 0.00001


@dataclass(frozen=True)
class LedgerFill:
    side: str  # BUY | SELL
    xrp_amount: float
    rlusd_amount: float
    price_rlusd_per_xrp: float
    tx_hash: str
    ledger_index: int
    source: str = "ledger"


@dataclass
class LedgerFillCursor:
    seen_tx_hashes: Set[str] = field(default_factory=set)
    max_seen: int = 500

    def remember(self, tx_hash: str) -> None:
        self.seen_tx_hashes.add(tx_hash)
        if len(self.seen_tx_hashes) > self.max_seen:
            # Drop oldest-ish entries (set order undefined — trim arbitrary excess).
            excess = len(self.seen_tx_hashes) - self.max_seen
            for _ in range(excess):
                self.seen_tx_hashes.pop()

    def is_new(self, tx_hash: str) -> bool:
        return bool(tx_hash) and tx_hash not in self.seen_tx_hashes


def _node_entry(node: Dict[str, Any]) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    for key in ("ModifiedNode", "DeletedNode", "CreatedNode"):
        if key in node:
            inner = node[key]
            return inner.get("LedgerEntryType"), inner
    return None, None


def _parse_xrp_drops(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, str):
        try:
            from xrpl.utils import drops_to_xrp

            return float(drops_to_xrp(value))
        except Exception:
            try:
                return float(value) / 1_000_000.0
            except (TypeError, ValueError):
                return 0.0
    if isinstance(value, (int, float)):
        return float(value) / 1_000_000.0
    return 0.0


def _balance_deltas_from_meta(
    meta: Dict[str, Any],
    *,
    account: str,
    rlusd_currency: str,
    rlusd_issuer: str,
) -> tuple[float, float]:
    """Return (xrp_delta, rlusd_delta) for the bot account from tx meta."""
    xrp_delta = 0.0
    rlusd_delta = 0.0
    for node in meta.get("AffectedNodes", []):
        entry_type, inner = _node_entry(node)
        if not inner:
            continue
        fields = inner.get("FinalFields") or inner.get("NewFields") or {}
        previous = inner.get("PreviousFields") or {}

        if entry_type == "AccountRoot" and fields.get("Account") == account:
            prev_bal = _parse_xrp_drops(previous.get("Balance", fields.get("Balance")))
            final_bal = _parse_xrp_drops(fields.get("Balance"))
            if previous:
                xrp_delta += final_bal - prev_bal
        elif entry_type == "RippleState":
            high = fields.get("HighLimit") or {}
            low = fields.get("LowLimit") or {}
            high_acct = high.get("account")
            low_acct = low.get("account")
            if account not in (high_acct, low_acct):
                continue
            issuer = high.get("issuer") or low.get("issuer")
            if issuer and issuer != rlusd_issuer:
                continue
            prev_bal = float(previous.get("Balance", fields.get("Balance", 0)) or 0)
            final_bal = float(fields.get("Balance", 0) or 0)
            if previous:
                rlusd_delta += final_bal - prev_bal
    return xrp_delta, rlusd_delta


def parse_ledger_fill_from_tx(
    tx_entry: Dict[str, Any],
    *,
    account: str,
    rlusd_currency: str,
    rlusd_issuer: str,
) -> Optional[LedgerFill]:
    """
    Infer a trade-like balance change from one account_tx row.

    Skips OfferCancel and bot-initiated OfferCreate (no meaningful RLUSD delta).
    """
    tx = tx_entry.get("tx") or {}
    meta = tx_entry.get("meta") or {}
    if isinstance(meta, str):
        return None
    if meta.get("TransactionResult") not in (None, "tesSUCCESS"):
        return None

    tx_type = tx.get("TransactionType", "")
    if tx_type == "OfferCancel":
        return None

    tx_hash = str(tx_entry.get("hash") or tx.get("hash") or "")
    ledger_index = int(tx_entry.get("ledger_index") or tx.get("ledger_index") or 0)

    xrp_delta, rlusd_delta = _balance_deltas_from_meta(
        meta,
        account=account,
        rlusd_currency=rlusd_currency,
        rlusd_issuer=rlusd_issuer,
    )

    # Bot OfferCreate without fill: typically only reserve/fee XRP movement.
    if tx_type == "OfferCreate" and tx.get("Account") == account:
        if abs(rlusd_delta) < MIN_RLUSD_DELTA:
            return None

    if abs(rlusd_delta) < MIN_RLUSD_DELTA and abs(xrp_delta) < MIN_XRP_DELTA:
        return None

    if rlusd_delta > MIN_RLUSD_DELTA:
        side = "SELL"
        rlusd_amount = rlusd_delta
        xrp_amount = abs(xrp_delta) if abs(xrp_delta) >= MIN_XRP_DELTA else (
            rlusd_amount / 1.0
        )
    elif rlusd_delta < -MIN_RLUSD_DELTA:
        side = "BUY"
        rlusd_amount = abs(rlusd_delta)
        xrp_amount = abs(xrp_delta) if abs(xrp_delta) >= MIN_XRP_DELTA else (
            rlusd_amount / 1.0
        )
    elif xrp_delta > MIN_XRP_DELTA:
        return None
    else:
        return None

    if xrp_amount <= 0:
        return None
    price = rlusd_amount / xrp_amount if side == "SELL" else rlusd_amount / xrp_amount
    if price <= 0:
        return None

    return LedgerFill(
        side=side,
        xrp_amount=xrp_amount,
        rlusd_amount=rlusd_amount,
        price_rlusd_per_xrp=price,
        tx_hash=tx_hash,
        ledger_index=ledger_index,
    )


class LedgerFillScanner:
    """Poll account_tx and emit new ledger-confirmed fills."""

    def __init__(self, cursor_path: str = "logs/ledger_fill_cursor.json") -> None:
        self.cursor_path = Path(cursor_path)
        self.cursor = self._load_cursor()

    def _load_cursor(self) -> LedgerFillCursor:
        if not self.cursor_path.exists():
            return LedgerFillCursor()
        try:
            data = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            hashes = set(data.get("seen_tx_hashes", []))
            return LedgerFillCursor(seen_tx_hashes=hashes)
        except (json.JSONDecodeError, OSError, TypeError):
            return LedgerFillCursor()

    def save(self) -> None:
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen_tx_hashes": sorted(self.cursor.seen_tx_hashes)[-self.cursor.max_seen :]}
        self.cursor_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def scan_transactions(
        self,
        transactions: List[Dict[str, Any]],
        *,
        account: str,
        rlusd_currency: str,
        rlusd_issuer: str,
    ) -> List[LedgerFill]:
        fills: List[LedgerFill] = []
        for entry in transactions:
            tx_hash = str(entry.get("hash") or (entry.get("tx") or {}).get("hash") or "")
            if not self.cursor.is_new(tx_hash):
                continue
            fill = parse_ledger_fill_from_tx(
                entry,
                account=account,
                rlusd_currency=rlusd_currency,
                rlusd_issuer=rlusd_issuer,
            )
            if fill:
                fills.append(fill)
            if tx_hash:
                self.cursor.remember(tx_hash)
        if fills:
            self.save()
        return fills
