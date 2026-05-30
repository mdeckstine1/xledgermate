"""Track inferred fill quality with multi-horizon markout."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, List, Optional


@dataclass
class FillRecord:
    side: str
    xrp_amount: float
    price: float
    mid_at_fill: float
    filled_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    mid_after: Optional[float] = None
    markout_30s: Optional[float] = None
    markout_5m: Optional[float] = None
    toxic_cycle: Optional[bool] = None
    toxic_30s: Optional[bool] = None
    toxic_5m: Optional[bool] = None
    tx_hash: str = ""
    fill_source: str = "balance_delta"


@dataclass
class FillQualityState:
    score: float = 100.0
    recent_fills: int = 0
    toxic_fills: int = 0
    toxic_ratio: float = 0.0
    toxic_fills_30s: int = 0
    toxic_ratio_30s: float = 0.0
    mean_markout_30s_pct: float = 0.0
    size_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    summary: str = "No recent fills"


class FillQualityTracker:
    """Rolling markout from fills + mid at +30s / +5m horizons."""

    def __init__(self, max_records: int = 20) -> None:
        self._pending: Optional[FillRecord] = None
        self._markout_pending: List[FillRecord] = []
        self._records: Deque[FillRecord] = deque(maxlen=max_records)
        self._toxic_threshold_pct: float = 0.04

    def set_toxic_threshold_pct(self, threshold: float) -> None:
        self._toxic_threshold_pct = max(0.01, float(threshold))

    @staticmethod
    def _is_toxic(side: str, move_pct: float, threshold: float) -> bool:
        if side == "SELL":
            return move_pct > threshold
        if side == "BUY":
            return move_pct < -threshold
        return False

    def note_fill(
        self,
        *,
        side: str,
        xrp_amount: float,
        price: float,
        mid_at_fill: float,
        tx_hash: str = "",
        fill_source: str = "balance_delta",
        filled_at: Optional[datetime] = None,
    ) -> None:
        now = filled_at or datetime.now(tz=timezone.utc)
        rec = FillRecord(
            side=side.upper(),
            xrp_amount=xrp_amount,
            price=price,
            mid_at_fill=mid_at_fill,
            filled_at=now,
            tx_hash=tx_hash,
            fill_source=fill_source,
        )
        self._pending = rec
        self._markout_pending.append(rec)

    def note_mid(self, mid: float, now: Optional[datetime] = None) -> None:
        if mid <= 0:
            return
        ts = now or datetime.now(tz=timezone.utc)

        if self._pending is not None and self._pending.mid_after is None:
            rec = self._pending
            rec.mid_after = mid
            move_pct = ((mid - rec.mid_at_fill) / rec.mid_at_fill) * 100.0
            rec.toxic_cycle = self._is_toxic(
                rec.side, move_pct, self._toxic_threshold_pct
            )
            self._pending = None

        still_pending: List[FillRecord] = []
        for rec in self._markout_pending:
            if rec.mid_at_fill <= 0:
                continue
            elapsed = (ts - rec.filled_at).total_seconds()
            move_pct = ((mid - rec.mid_at_fill) / rec.mid_at_fill) * 100.0
            if rec.markout_30s is None and elapsed >= 30.0:
                rec.markout_30s = move_pct
                rec.toxic_30s = self._is_toxic(
                    rec.side, move_pct, self._toxic_threshold_pct
                )
            if rec.markout_5m is None and elapsed >= 300.0:
                rec.markout_5m = move_pct
                rec.toxic_5m = self._is_toxic(
                    rec.side, move_pct, self._toxic_threshold_pct
                )
            if rec.markout_5m is not None:
                self._records.append(rec)
            else:
                still_pending.append(rec)
        self._markout_pending = still_pending

    def _toxic_for_record(self, rec: FillRecord) -> bool:
        if rec.toxic_30s is not None:
            return rec.toxic_30s
        if rec.toxic_5m is not None:
            return rec.toxic_5m
        if rec.toxic_cycle is not None:
            return rec.toxic_cycle
        return False

    def assess(self) -> FillQualityState:
        active = list(self._records) + [
            r
            for r in self._markout_pending
            if r.markout_30s is not None or r.mid_after is not None
        ]
        if not active:
            return FillQualityState(summary="No recent fills")

        toxic = sum(1 for rec in active if self._toxic_for_record(rec))
        toxic_30s = sum(1 for rec in active if rec.toxic_30s)
        markouts_30s = [rec.markout_30s for rec in active if rec.markout_30s is not None]
        n = len(active)
        toxic_ratio = toxic / n if n else 0.0
        toxic_ratio_30s = toxic_30s / len(markouts_30s) if markouts_30s else toxic_ratio
        mean_markout_30s = (
            sum(markouts_30s) / len(markouts_30s) if markouts_30s else 0.0
        )
        score = max(0.0, 100.0 - toxic_ratio * 60.0 - (n * 2.0))

        size_mult = 1.0
        spread_mult = 1.0
        if toxic_ratio >= 0.5:
            size_mult = 0.55
            spread_mult = 1.25
            summary = (
                f"Fill quality poor ({toxic}/{n} adverse, "
                f"30s ratio {toxic_ratio_30s:.0%}) → defensive"
            )
        elif toxic_ratio >= 0.25:
            size_mult = 0.75
            spread_mult = 1.12
            summary = (
                f"Fill quality mixed ({toxic}/{n} adverse, "
                f"30s ratio {toxic_ratio_30s:.0%}) → cautious"
            )
        else:
            summary = (
                f"Fill quality OK ({n} fills, {toxic} adverse, "
                f"30s mean markout {mean_markout_30s:+.3f}%)"
            )

        return FillQualityState(
            score=score,
            recent_fills=n,
            toxic_fills=toxic,
            toxic_ratio=toxic_ratio,
            toxic_fills_30s=toxic_30s,
            toxic_ratio_30s=toxic_ratio_30s,
            mean_markout_30s_pct=mean_markout_30s,
            size_multiplier=size_mult,
            spread_multiplier=spread_mult,
            summary=summary,
        )

    def recent_summaries(self, limit: int = 5) -> List[str]:
        out: List[str] = []
        for rec in list(self._records)[-limit:]:
            parts = [f"{rec.side} {rec.xrp_amount:.2f} XRP @ {rec.price:.4f}"]
            if rec.markout_30s is not None:
                parts.append(f"30s {rec.markout_30s:+.3f}%")
            elif rec.mid_after is not None and rec.mid_at_fill > 0:
                move = ((rec.mid_after - rec.mid_at_fill) / rec.mid_at_fill) * 100.0
                parts.append(f"cycle {move:+.3f}%")
            if rec.tx_hash:
                parts.append(f"tx {rec.tx_hash[:8]}…")
            out.append(" → ".join(parts))
        return out
