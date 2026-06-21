"""A2.3c — cancel open asks immediately when ask brakes engage (stale ledger leak)."""

from __future__ import annotations

from typing import List, Sequence

from connectors.xrpl_connector import OpenOffer


def ask_brake_cancel_sequences(
    open_offers: Sequence[OpenOffer],
    *,
    pause_asks: bool,
) -> List[int]:
    """Force-cancel all resting asks when pause_asks is active (do not wait for A3 max-age)."""
    if not pause_asks:
        return []
    out: List[int] = []
    seen: set[int] = set()
    for offer in open_offers:
        if (offer.side or "").strip().lower() != "ask":
            continue
        seq = int(offer.sequence)
        if seq in seen:
            continue
        seen.add(seq)
        out.append(seq)
    return out


__all__ = ["ask_brake_cancel_sequences"]
