"""Selective order refresh — preserve queue when quotes unchanged."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Set

from core.runtime_state import QuoteIntent
from connectors.xrpl_connector import OpenOffer


@dataclass(frozen=True)
class OrderSyncPlan:
    """Which offers to keep, cancel, and which intents still need placement."""

    matched_sequences: Set[int]
    cancel_sequences: List[int]
    place_intents: List[QuoteIntent]
    kept_count: int


def _price_within_tolerance(
    intent_price: float,
    offer_price: float,
    *,
    tol_pct: float,
) -> bool:
    if offer_price <= 0:
        return False
    diff_pct = abs(intent_price - offer_price) / offer_price * 100.0
    return diff_pct <= tol_pct


def _size_within_tolerance(intent_size: float, offer_size: float, *, tol_xrp: float) -> bool:
    return abs(intent_size - offer_size) <= tol_xrp


def plan_order_sync(
    intents: Sequence[QuoteIntent],
    open_offers: Sequence[OpenOffer],
    *,
    price_tolerance_pct: float = 0.08,
    size_tolerance_xrp: float = 0.75,
) -> OrderSyncPlan:
    """
    Match planned intents to open offers by side + price/size proximity.
    Unmatched offers are cancelled; unmatched intents are placed fresh.
    """
    remaining = list(open_offers)
    matched_sequences: Set[int] = set()
    place_intents: List[QuoteIntent] = []

    for intent in intents:
        best_idx: Optional[int] = None
        best_score = float("inf")
        for idx, offer in enumerate(remaining):
            if offer.side != intent.side:
                continue
            if not _price_within_tolerance(
                intent.price, offer.price, tol_pct=price_tolerance_pct
            ):
                continue
            if not _size_within_tolerance(
                intent.size_xrp, offer.size_xrp, tol_xrp=size_tolerance_xrp
            ):
                continue
            score = abs(intent.price - offer.price) + abs(intent.size_xrp - offer.size_xrp)
            if score < best_score:
                best_score = score
                best_idx = idx

        if best_idx is not None:
            offer = remaining.pop(best_idx)
            matched_sequences.add(offer.sequence)
        else:
            place_intents.append(intent)

    cancel_sequences = [o.sequence for o in open_offers if o.sequence not in matched_sequences]
    return OrderSyncPlan(
        matched_sequences=matched_sequences,
        cancel_sequences=cancel_sequences,
        place_intents=place_intents,
        kept_count=len(matched_sequences),
    )
