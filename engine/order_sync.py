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


def _offer_competitive_vs_touch(
    offer: OpenOffer,
    *,
    best_bid: float | None,
    best_ask: float | None,
    max_worse_than_touch_pct: float,
    max_improve_touch_pct: float = 0.15,
) -> bool:
    """True when an existing offer is still fillable vs the live touch (preserve queue)."""
    if offer.side == "bid":
        if best_bid is None or best_bid <= 0:
            return False
        vs_touch = (offer.price - best_bid) / best_bid * 100.0
        return -max_worse_than_touch_pct <= vs_touch <= max_improve_touch_pct
    if best_ask is None or best_ask <= 0:
        return False
    vs_touch = (offer.price - best_ask) / best_ask * 100.0
    return -max_improve_touch_pct <= vs_touch <= max_worse_than_touch_pct


def plan_order_sync(
    intents: Sequence[QuoteIntent],
    open_offers: Sequence[OpenOffer],
    *,
    price_tolerance_pct: float = 0.08,
    size_tolerance_xrp: float = 0.75,
    best_bid: float | None = None,
    best_ask: float | None = None,
    max_worse_than_touch_pct: float | None = None,
    preserve_queue_max_worse_pct: float | None = None,
    max_improve_touch_pct: float = 0.15,
    preserve_touch_queue: bool = False,
) -> OrderSyncPlan:
    """
    Match planned intents to open offers by side + price/size proximity.
    Unmatched offers are cancelled; unmatched intents are placed fresh.
    """
    queue_worse_pct = (
        preserve_queue_max_worse_pct
        if preserve_queue_max_worse_pct is not None
        else max_worse_than_touch_pct
    )
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
        elif (
            preserve_touch_queue
            and intent.level == 1
            and queue_worse_pct is not None
            and best_bid is not None
            and best_ask is not None
        ):
            for idx, offer in enumerate(remaining):
                if offer.side != intent.side:
                    continue
                if not _offer_competitive_vs_touch(
                    offer,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    max_worse_than_touch_pct=queue_worse_pct,
                    max_improve_touch_pct=max_improve_touch_pct,
                ):
                    continue
                if not _size_within_tolerance(
                    intent.size_xrp, offer.size_xrp, tol_xrp=size_tolerance_xrp
                ):
                    continue
                offer = remaining.pop(idx)
                matched_sequences.add(offer.sequence)
                break
            else:
                place_intents.append(intent)
        else:
            place_intents.append(intent)

    cancel_sequences = [o.sequence for o in open_offers if o.sequence not in matched_sequences]
    return OrderSyncPlan(
        matched_sequences=matched_sequences,
        cancel_sequences=cancel_sequences,
        place_intents=place_intents,
        kept_count=len(matched_sequences),
    )


def offers_off_touch(
    open_offers: Sequence[OpenOffer],
    *,
    best_bid: float | None,
    best_ask: float | None,
    max_worse_than_touch_pct: float = 0.08,
) -> bool:
    """True when any open offer is too far from touch to plausibly fill."""
    for offer in open_offers:
        if not _offer_competitive_vs_touch(
            offer,
            best_bid=best_bid,
            best_ask=best_ask,
            max_worse_than_touch_pct=max_worse_than_touch_pct,
        ):
            return True
    return False
