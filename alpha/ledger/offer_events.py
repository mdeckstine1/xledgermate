"""Detect offer cancel vs fill from XRPL account transaction stream."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _tx_from_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tx = message.get("transaction")
    return tx if isinstance(tx, dict) else None


def offer_cancel_seen(recent_messages: List[Dict[str, Any]], offer_sequence: int) -> bool:
    """True if a recent account tx is OfferCancel for ``offer_sequence``."""
    if offer_sequence <= 0:
        return False
    for message in recent_messages:
        tx = _tx_from_message(message)
        if tx is None:
            continue
        if tx.get("TransactionType") != "OfferCancel":
            continue
        cancelled = tx.get("OfferSequence")
        if cancelled is None:
            meta = message.get("meta") or {}
            for node in meta.get("AffectedNodes") or []:
                deleted = node.get("DeletedNode") or {}
                entry = deleted.get("FinalFields") or deleted.get("PreviousFields") or {}
                if entry.get("LedgerEntryType") == "Offer":
                    prev = deleted.get("PreviousFields") or {}
                    seq = prev.get("Sequence") or entry.get("Sequence")
                    if seq is not None and int(seq) == offer_sequence:
                        return True
            continue
        if int(cancelled) == int(offer_sequence):
            return True
    return False
