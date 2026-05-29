"""Track inferred fill quality and dampen aggressiveness after toxic fills."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional


@dataclass
class FillRecord:
    side: str
    xrp_amount: float
    price: float
    mid_at_fill: float
    mid_after: Optional[float] = None


@dataclass
class FillQualityState:
    score: float = 100.0
    recent_fills: int = 0
    toxic_fills: int = 0
    size_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    summary: str = "No recent fills"


class FillQualityTracker:
    """Rolling markout proxy from balance-delta fills + subsequent mid moves."""

    def __init__(self, max_records: int = 20) -> None:
        self._pending: Optional[FillRecord] = None
        self._records: Deque[FillRecord] = deque(maxlen=max_records)

    def note_fill(
        self,
        *,
        side: str,
        xrp_amount: float,
        price: float,
        mid_at_fill: float,
    ) -> None:
        self._pending = FillRecord(
            side=side.upper(),
            xrp_amount=xrp_amount,
            price=price,
            mid_at_fill=mid_at_fill,
        )

    def note_mid(self, mid: float) -> None:
        if self._pending is None or mid <= 0:
            return
        rec = self._pending
        rec.mid_after = mid
        self._records.append(rec)
        self._pending = None

    def assess(self) -> FillQualityState:
        if not self._records:
            return FillQualityState(summary="No recent fills")

        toxic = 0
        for rec in self._records:
            if rec.mid_after is None or rec.mid_at_fill <= 0:
                continue
            move_pct = ((rec.mid_after - rec.mid_at_fill) / rec.mid_at_fill) * 100.0
            if rec.side == "SELL" and move_pct > 0.04:
                toxic += 1
            elif rec.side == "BUY" and move_pct < -0.04:
                toxic += 1

        n = len(self._records)
        toxic_ratio = toxic / n if n else 0.0
        score = max(0.0, 100.0 - toxic_ratio * 60.0 - (n * 2.0))

        size_mult = 1.0
        spread_mult = 1.0
        if toxic_ratio >= 0.5:
            size_mult = 0.55
            spread_mult = 1.25
            summary = f"Fill quality poor ({toxic}/{n} adverse) → defensive"
        elif toxic_ratio >= 0.25:
            size_mult = 0.75
            spread_mult = 1.12
            summary = f"Fill quality mixed ({toxic}/{n} adverse) → cautious"
        else:
            summary = f"Fill quality OK ({n} recent fills, {toxic} adverse)"

        return FillQualityState(
            score=score,
            recent_fills=n,
            toxic_fills=toxic,
            size_multiplier=size_mult,
            spread_multiplier=spread_mult,
            summary=summary,
        )

    def recent_summaries(self, limit: int = 5) -> List[str]:
        out: List[str] = []
        for rec in list(self._records)[-limit:]:
            if rec.mid_after is None:
                continue
            move = ((rec.mid_after - rec.mid_at_fill) / rec.mid_at_fill) * 100.0
            out.append(f"{rec.side} {rec.xrp_amount:.2f} XRP @ {rec.price:.4f} → mid {move:+.3f}%")
        return out
