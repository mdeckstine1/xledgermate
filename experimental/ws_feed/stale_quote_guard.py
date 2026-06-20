"""A3 — auto-cancel stale quotes before toxic fill-age tail (M6 + OfferAgeTracker)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

from connectors.xrpl_connector import OpenOffer
from experimental.ws_feed.offer_age_tracker import OfferAgeTracker

# Aligned with ws_pure_engine.WS_MID_MOVE_REFRESH_BPS
WS_MID_MOVE_REFRESH_BPS = 8.0

WS_MAX_QUOTE_AGE_ASK_S = 60.0
WS_MAX_QUOTE_AGE_BID_S = 90.0

WS_TOXIC_ASK_AGE_THRESHOLD = 0.25
WS_TOXIC_ASK_MAX_AGE_S = 45.0

WS_MID_MOVE_STALE_AGE_S = 30.0


@dataclass(frozen=True)
class StaleQuoteCancelDecision:
    sequence: int
    side: str
    age_seconds: float
    reason: str


def _mid_move_bps(
    mid: Optional[float],
    last_sync_mid: Optional[float],
) -> float:
    if not mid or not last_sync_mid or last_sync_mid <= 0:
        return 0.0
    return abs(mid - last_sync_mid) / last_sync_mid * 10_000.0


def _max_age_for_side(side: str, *, toxic_ratio_30s: float) -> Optional[float]:
    key = (side or "").strip().lower()
    if key == "ask":
        if toxic_ratio_30s >= WS_TOXIC_ASK_AGE_THRESHOLD:
            return WS_TOXIC_ASK_MAX_AGE_S
        return WS_MAX_QUOTE_AGE_ASK_S
    if key == "bid":
        return WS_MAX_QUOTE_AGE_BID_S
    return None


def _offer_age_seconds(
    offer: OpenOffer,
    offer_age: OfferAgeTracker,
    *,
    now: datetime,
) -> Optional[float]:
    age = offer_age.age_seconds_at(
        offer.side,
        detected_utc=now,
        sequence=offer.sequence,
    )
    if age is not None:
        return age
    return offer_age.age_seconds_at(offer.side, detected_utc=now)


def stale_quote_cancel_decisions(
    open_offers: Sequence[OpenOffer],
    offer_age: OfferAgeTracker,
    *,
    now: datetime,
    toxic_ratio_30s: float,
    mid: Optional[float] = None,
    last_sync_mid: Optional[float] = None,
    mid_move_refresh_bps: float = WS_MID_MOVE_REFRESH_BPS,
) -> List[StaleQuoteCancelDecision]:
    """Return per-offer stale-quote cancel decisions (deduped by sequence)."""
    move_bps = _mid_move_bps(mid, last_sync_mid)
    mid_move_stale = move_bps >= mid_move_refresh_bps
    toxic = float(toxic_ratio_30s)
    seen: set[int] = set()
    out: List[StaleQuoteCancelDecision] = []

    for offer in open_offers:
        seq = int(offer.sequence)
        if seq in seen:
            continue
        age = _offer_age_seconds(offer, offer_age, now=now)
        if age is None:
            continue
        side = (offer.side or "").strip().lower()
        max_age = _max_age_for_side(side, toxic_ratio_30s=toxic)
        reason: Optional[str] = None
        if max_age is not None and age > max_age:
            cap_label = f"{max_age:.0f}s"
            if side == "ask" and toxic >= WS_TOXIC_ASK_AGE_THRESHOLD:
                cap_label = f"{max_age:.0f}s toxic"
            reason = f"max_age age={age:.0f}s (max={cap_label})"
        elif mid_move_stale and age > WS_MID_MOVE_STALE_AGE_S:
            reason = (
                f"mid_move age={age:.0f}s move={move_bps:.1f}bps"
                f" (>{mid_move_refresh_bps:.0f}bps)"
            )
        if reason is None:
            continue
        seen.add(seq)
        out.append(
            StaleQuoteCancelDecision(
                sequence=seq,
                side=side,
                age_seconds=age,
                reason=reason,
            )
        )
    return out


def stale_quote_sequences_to_cancel(
    open_offers: Sequence[OpenOffer],
    offer_age: OfferAgeTracker,
    *,
    now: datetime,
    toxic_ratio_30s: float,
    mid: Optional[float] = None,
    last_sync_mid: Optional[float] = None,
    mid_move_refresh_bps: float = WS_MID_MOVE_REFRESH_BPS,
) -> List[int]:
    """Deduped offer sequence IDs to force-cancel for stale-quote tail (A3)."""
    decisions = stale_quote_cancel_decisions(
        open_offers,
        offer_age,
        now=now,
        toxic_ratio_30s=toxic_ratio_30s,
        mid=mid,
        last_sync_mid=last_sync_mid,
        mid_move_refresh_bps=mid_move_refresh_bps,
    )
    return [d.sequence for d in decisions]
