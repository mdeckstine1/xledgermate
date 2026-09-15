"""FX session clock for Maximize — Tokyo / London / NY opens, not a trailing 24h bag."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from alpha.types import utc_now

# Crypto follows FX vol clusters. UTC hours:
#   00:00 Tokyo/Asia  ·  07:00 London  ·  13:00 New York
# Overlaps (high vol): 07:00–09:00 Tokyo–London, 13:00–16:00 London–NY.
DEFAULT_SESSION_OPENS_UTC: tuple[int, ...] = (0, 7, 13)
_SESSION_NAMES = {0: "tokyo", 7: "london", 13: "new_york"}


@dataclass(frozen=True)
class FxSession:
    name: str
    open_utc: datetime
    next_open_utc: datetime
    hours_elapsed: float
    open_hour: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "open_hour_utc": self.open_hour,
            "open_utc": self.open_utc.isoformat(),
            "next_open_utc": self.next_open_utc.isoformat(),
            "hours_elapsed": round(self.hours_elapsed, 3),
        }


def parse_session_opens(raw: object) -> tuple[int, ...]:
    if isinstance(raw, (list, tuple)):
        hours = [int(h) for h in raw]
    elif isinstance(raw, str) and raw.strip():
        hours = [int(p.strip()) for p in raw.split(",") if p.strip()]
    else:
        hours = list(DEFAULT_SESSION_OPENS_UTC)
    cleaned = sorted({h % 24 for h in hours})
    return tuple(cleaned) if cleaned else DEFAULT_SESSION_OPENS_UTC


def current_fx_session(
    now: datetime | None = None,
    *,
    opens_utc: Sequence[int] | None = None,
) -> FxSession:
    ts = now or utc_now()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    opens = tuple(opens_utc) if opens_utc else DEFAULT_SESSION_OPENS_UTC
    opens = parse_session_opens(opens)
    day0 = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    stamps: list[datetime] = []
    for delta_day in (-1, 0, 1):
        base = day0 + timedelta(days=delta_day)
        for hour in opens:
            stamps.append(base + timedelta(hours=hour))
    stamps.sort()
    open_at = stamps[0]
    nxt = stamps[1]
    for i, stamp in enumerate(stamps):
        if stamp <= ts:
            open_at = stamp
            nxt = stamps[min(i + 1, len(stamps) - 1)]
        else:
            nxt = stamp
            break
    elapsed = max(0.0, (ts - open_at).total_seconds() / 3600.0)
    name = _SESSION_NAMES.get(open_at.hour, f"h{open_at.hour:02d}")
    return FxSession(
        name=name,
        open_utc=open_at,
        next_open_utc=nxt,
        hours_elapsed=elapsed,
        open_hour=open_at.hour,
    )


def move_window_hours(config: object, *, now: datetime | None = None) -> tuple[float, str]:
    """Hours of price history for harvest/dip/down-leg. Session clock when enabled."""
    enabled = bool(getattr(config, "alpha_fx_session_clock_enabled", True))
    fallback = float(getattr(config, "alpha_accumulation_harvest_move_hours", 24.0) or 24.0)
    if not enabled:
        return max(0.5, fallback), "24h"
    opens = parse_session_opens(getattr(config, "alpha_fx_session_opens_utc", "0,7,13"))
    sess = current_fx_session(now, opens_utc=opens)
    # Floor so a brand-new open still has a few samples.
    return max(0.35, sess.hours_elapsed), sess.name
