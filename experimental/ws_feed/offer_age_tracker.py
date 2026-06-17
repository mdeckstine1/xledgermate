"""Lab prep for M2 — track quote placement time per side for detected-fill age."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class OfferAgeTracker:
    """
    v1: last-place timestamp per side (bid/ask).

    Production M2 will extend with per-sequence tracking (M6) after soak data review.
    """

    _placed_utc: Dict[str, datetime] = field(default_factory=dict)
    _last_sequence: Dict[str, int] = field(default_factory=dict)

    def record_place(
        self,
        side: str,
        *,
        placed_utc: Optional[datetime] = None,
        sequence: Optional[int] = None,
    ) -> None:
        key = (side or "").strip().lower()
        if key not in ("bid", "ask"):
            return
        self._placed_utc[key] = placed_utc or _utc_now()
        if sequence is not None:
            self._last_sequence[key] = int(sequence)

    def last_placed_utc(self, side: str) -> Optional[datetime]:
        return self._placed_utc.get((side or "").strip().lower())

    def age_seconds_at(
        self,
        side: str,
        *,
        detected_utc: Optional[datetime] = None,
    ) -> Optional[float]:
        """Seconds from last place on side to detected fill time."""
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
    ) -> Optional[float]:
        """Alias for M2 HUD/CSV field name."""
        return self.age_seconds_at(side, detected_utc=fill_detected_utc)

    def clear_side(self, side: str) -> None:
        key = (side or "").strip().lower()
        self._placed_utc.pop(key, None)
        self._last_sequence.pop(key, None)

    def snapshot(self) -> Dict[str, object]:
        return {
            "bid_placed_utc": self._placed_utc.get("bid").isoformat() if self._placed_utc.get("bid") else None,
            "ask_placed_utc": self._placed_utc.get("ask").isoformat() if self._placed_utc.get("ask") else None,
            "bid_sequence": self._last_sequence.get("bid"),
            "ask_sequence": self._last_sequence.get("ask"),
        }
