"""QD v2.2 — cancel resting offers immediately when a side is paused (stale ledger leak)."""

from __future__ import annotations

from typing import List, Sequence

from connectors.xrpl_connector import OpenOffer


def side_brake_cancel_sequences(
    open_offers: Sequence[OpenOffer],
    *,
    pause_bids: bool,
    pause_asks: bool,
) -> List[int]:
    """Force-cancel resting bids/asks when that side is paused (do not wait for A3 max-age)."""
    if not pause_bids and not pause_asks:
        return []
    out: List[int] = []
    seen: set[int] = set()
    for offer in open_offers:
        side = (offer.side or "").strip().lower()
        if side == "bid" and not pause_bids:
            continue
        if side == "ask" and not pause_asks:
            continue
        if side not in ("bid", "ask"):
            continue
        seq = int(offer.sequence)
        if seq in seen:
            continue
        seen.add(seq)
        out.append(seq)
    return out


def ask_brake_cancel_sequences(
    open_offers: Sequence[OpenOffer],
    *,
    pause_asks: bool,
) -> List[int]:
    """Backward-compatible wrapper — prefer side_brake_cancel_sequences."""
    return side_brake_cancel_sequences(
        open_offers, pause_bids=False, pause_asks=pause_asks
    )


__all__ = ["ask_brake_cancel_sequences", "side_brake_cancel_sequences"]
