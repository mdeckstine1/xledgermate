"""QD v2.2 — cancel resting offers when a side is not allowed (stale ledger leak)."""

from __future__ import annotations

from typing import List, Sequence

from connectors.xrpl_connector import OpenOffer


def side_brake_cancel_sequences(
    open_offers: Sequence[OpenOffer],
    *,
    bid_allowed: bool,
    ask_allowed: bool,
) -> List[int]:
    """Force-cancel resting bids/asks when QD blocks that side."""
    if bid_allowed and ask_allowed:
        return []
    out: List[int] = []
    seen: set[int] = set()
    for offer in open_offers:
        side = (offer.side or "").strip().lower()
        if side == "bid" and bid_allowed:
            continue
        if side == "ask" and ask_allowed:
            continue
        if side not in ("bid", "ask"):
            continue
        seq = int(offer.sequence)
        if seq in seen:
            continue
        seen.add(seq)
        out.append(seq)
    return out


__all__ = ["side_brake_cancel_sequences"]
