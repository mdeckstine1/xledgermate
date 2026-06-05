from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from connectors.xrpl_connector import XRPLConnector


def _is_xrp_leg(amount: Any) -> bool:
    if isinstance(amount, str):
        return True
    if isinstance(amount, dict):
        cur = str(amount.get("currency", "")).upper()
        return cur in ("XRP", "")
    return False


def _is_rlusd_leg(amount: Any, pair_issuer: str) -> bool:
    if not isinstance(amount, dict):
        return False
    issuer = str(amount.get("issuer", ""))
    if issuer != pair_issuer:
        return False
    cur = str(amount.get("currency", ""))
    return cur.startswith("524C555344") or cur in ("RLUSD", "USD")


def _side_from_subscribe_book(
    taker_gets: Any, taker_pays: Any, pair_issuer: str
) -> Optional[str]:
    """Infer ask vs bid from subscribe book legs (XRP/RLUSD pair)."""
    gets = XRPLConnector._coerce_ledger_amount(taker_gets)
    pays = XRPLConnector._coerce_ledger_amount(taker_pays)
    if _is_xrp_leg(gets) and _is_rlusd_leg(pays, pair_issuer):
        return "ask"
    if _is_rlusd_leg(gets, pair_issuer) and _is_xrp_leg(pays):
        return "bid"
    return None


def extract_offers_from_message(
    message: Dict[str, Any],
    *,
    rlusd_issuer: str,
) -> List[Tuple[str, List[dict], bool]]:
    """
    Return list of (side, raw_offers, deleted) tuples from a rippled WS payload.
    """
    out: List[Tuple[str, List[dict], bool]] = []
    if not isinstance(message, dict):
        return out

    msg_type = message.get("type")
    if msg_type == "response":
        result = message.get("result") or {}
        if isinstance(result, dict) and result.get("offers"):
            side = _side_from_subscribe_book(
                result.get("taker_gets"),
                result.get("taker_pays"),
                rlusd_issuer,
            )
            if side:
                offers = result.get("offers") or []
                if isinstance(offers, list):
                    out.append((side, offers, False))
        return out

    if msg_type != "transaction":
        return out

    tx = message.get("transaction") or {}
    meta = message.get("meta") or {}
    if not isinstance(tx, dict) or not isinstance(meta, dict):
        return out

    tx_type = tx.get("TransactionType") or tx.get("transaction_type")
    if tx_type not in ("OfferCreate", "OfferCancel"):
        return out

    affected = meta.get("AffectedNodes") or []
    if not isinstance(affected, list):
        return out

    for node in affected:
        if not isinstance(node, dict):
            continue
        fields = (
            node.get("ModifiedNode")
            or node.get("CreatedNode")
            or node.get("DeletedNode")
        )
        if not isinstance(fields, dict):
            continue
        if fields.get("LedgerEntryType") != "Offer":
            continue
        final = fields.get("FinalFields") or fields.get("NewFields") or {}
        prev = fields.get("PreviousFields") or {}
        if not isinstance(final, dict):
            final = {}
        if not isinstance(prev, dict):
            prev = {}

        gets = final.get("TakerGets") or prev.get("TakerGets")
        pays = final.get("TakerPays") or prev.get("TakerPays")
        if gets is None or pays is None:
            continue

        side = _side_from_subscribe_book(gets, pays, rlusd_issuer)
        if not side:
            continue

        deleted = "DeletedNode" in node or tx_type == "OfferCancel"
        offer_row = {
            "TakerGets": gets,
            "TakerPays": pays,
            "seq": final.get("Sequence") or prev.get("Sequence"),
        }
        out.append((side, [offer_row], deleted))

    return out


def normalize_snapshot_offers(
    connector: XRPLConnector,
    side: str,
    raw_offers: List[dict],
) -> List[Dict[str, float]]:
    return connector._normalize_offers(raw_offers, side=side)