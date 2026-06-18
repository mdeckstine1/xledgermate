"""M2/M6 — track quote placement time per side and per offer sequence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _norm_side(side: str) -> Optional[str]:
    key = (side or "").strip().lower()
    if key in ("bid", "ask"):
        return key
    return None


@dataclass
class OfferAgeTracker:
    """
    M2: last-place timestamp per side (bid/ask).
    M6: per-sequence timestamps; cleared on cancel; fill age prefers sequence map.
    """

    _placed_utc: Dict[str, datetime] = field(default_factory=dict)
    _last_sequence: Dict[str, int] = field(default_factory=dict)
    _by_sequence: Dict[int, datetime] = field(default_factory=dict)
    _sequence_side: Dict[int, str] = field(default_factory=dict)

    def record_place(
        self,
        side: str,
        *,
        placed_utc: Optional[datetime] = None,
        sequence: Optional[int] = None,
    ) -> None:
        key = _norm_side(side)
        if key is None:
            return
        when = placed_utc or _utc_now()
        self._placed_utc[key] = when
        if sequence is not None:
            seq = int(sequence)
            self._last_sequence[key] = seq
            self._by_sequence[seq] = when
            self._sequence_side[seq] = key

    def forget_sequence(self, sequence: int) -> None:
        """Remove a cancelled offer from per-sequence tracking (M6)."""
        seq = int(sequence)
        side = self._sequence_side.pop(seq, None)
        self._by_sequence.pop(seq, None)
        if not side:
            return
        remaining = [s for s, sd in self._sequence_side.items() if sd == side]
        if remaining:
            latest = max(remaining)
            self._last_sequence[side] = latest
            self._placed_utc[side] = self._by_sequence[latest]
        else:
            self._last_sequence.pop(side, None)
            self._placed_utc.pop(side, None)

    def last_placed_utc(self, side: str) -> Optional[datetime]:
        key = _norm_side(side)
        if key is None:
            return None
        seq = self._last_sequence.get(key)
        if seq is not None and seq in self._by_sequence:
            return self._by_sequence[seq]
        return self._placed_utc.get(key)

    def age_seconds_at(
        self,
        side: str,
        *,
        detected_utc: Optional[datetime] = None,
        sequence: Optional[int] = None,
    ) -> Optional[float]:
        """Seconds from placement to detected fill time."""
        placed: Optional[datetime] = None
        if sequence is not None:
            seq = int(sequence)
            placed = self._by_sequence.get(seq)
            if placed is None:
                return None
        elif side:
            placed = self.last_placed_utc(side)
        if placed is None:
            return None
        detected = detected_utc or _utc_now()
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        if placed.tzinfo is None:
            placed = placed.replace(tzinfo=timezone.utc)
        return max(0.0, (detected - placed).total_seconds())

    def effective_quote_age_at_fill_seconds(
        self,
        side: str,
        *,
        fill_detected_utc: Optional[datetime] = None,
        sequence: Optional[int] = None,
    ) -> Optional[float]:
        """M2 HUD/CSV field — prefers M6 sequence when known."""
        return self.age_seconds_at(
            side,
            detected_utc=fill_detected_utc,
            sequence=sequence,
        )

    def clear_side(self, side: str) -> None:
        key = _norm_side(side)
        if key is None:
            return
        self._placed_utc.pop(key, None)
        seq = self._last_sequence.pop(key, None)
        if seq is not None:
            self._by_sequence.pop(seq, None)
            self._sequence_side.pop(seq, None)

    def snapshot(self) -> Dict[str, object]:
        return {
            "bid_placed_utc": self._placed_utc.get("bid").isoformat() if self._placed_utc.get("bid") else None,
            "ask_placed_utc": self._placed_utc.get("ask").isoformat() if self._placed_utc.get("ask") else None,
            "bid_sequence": self._last_sequence.get("bid"),
            "ask_sequence": self._last_sequence.get("ask"),
            "tracked_sequences": len(self._by_sequence),
        }
