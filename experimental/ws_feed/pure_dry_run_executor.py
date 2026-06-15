"""
D2 — Dry-run offer sync for WS + pure A-S path.

Simulates place/cancel/replace from PureQuotePath quote_intents without
touching engine/trading_engine.py or the sacred VPS stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _intent_key(side: str, level: int) -> str:
    return f"{side}:{level}"


def _price_match(a: float, b: float, *, rel_tol: float = 0.0001) -> bool:
    if a <= 0 or b <= 0:
        return a == b
    return abs(a - b) <= max(a, b) * rel_tol


def _size_match(a: float, b: float, *, abs_tol: float = 0.05) -> bool:
    return abs(a - b) <= abs_tol


@dataclass
class VirtualOffer:
    side: str
    level: int
    price: float
    size_xrp: float
    placed_at_utc: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "level": self.level,
            "price": self.price,
            "size_xrp": self.size_xrp,
            "placed_at_utc": self.placed_at_utc,
        }


@dataclass
class DryRunOfferDiff:
    """Result of one dry-run sync cycle."""

    would_quote: bool
    to_place: List[Dict[str, Any]] = field(default_factory=list)
    to_cancel: List[Dict[str, Any]] = field(default_factory=list)
    unchanged: List[Dict[str, Any]] = field(default_factory=list)
    open_offers: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    cycle: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "would_quote": self.would_quote,
            "to_place": self.to_place,
            "to_cancel": self.to_cancel,
            "unchanged": self.unchanged,
            "open_offers": self.open_offers,
            "summary": self.summary,
            "cycle": self.cycle,
            "placed_count": len(self.to_place),
            "cancelled_count": len(self.to_cancel),
            "open_count": len(self.open_offers),
        }


def active_intents_from_ladder(
    quote_intents: Sequence[Dict[str, Any]],
    *,
    would_quote: bool,
) -> List[Dict[str, Any]]:
    """L1 active intents when quoting; empty when blocked."""
    if not would_quote:
        return []
    out: List[Dict[str, Any]] = []
    for row in quote_intents:
        if not row.get("active"):
            continue
        side = str(row.get("side", ""))
        level = int(row.get("level", 0))
        if side not in ("bid", "ask") or level < 1:
            continue
        out.append(row)
    return out


class PureDryRunExecutor:
    """Virtual open offers — mirrors sacred dry_run place/cancel logging."""

    def __init__(self) -> None:
        self._open: Dict[str, VirtualOffer] = {}
        self._cycle = 0

    @property
    def open_offers(self) -> List[VirtualOffer]:
        return list(self._open.values())

    def sync(
        self,
        quote_intents: Sequence[Dict[str, Any]],
        *,
        would_quote: bool,
    ) -> DryRunOfferDiff:
        self._cycle += 1
        targets = active_intents_from_ladder(quote_intents, would_quote=would_quote)
        target_map: Dict[str, Dict[str, Any]] = {}
        for row in targets:
            key = _intent_key(str(row["side"]), int(row["level"]))
            target_map[key] = row

        to_cancel: List[Dict[str, Any]] = []
        unchanged: List[Dict[str, Any]] = []
        to_place: List[Dict[str, Any]] = []

        for key, offer in list(self._open.items()):
            if key not in target_map:
                to_cancel.append(offer.as_dict())
                del self._open[key]
                continue
            tgt = target_map[key]
            price = float(tgt["price"])
            size = float(tgt.get("size_xrp", 0))
            if _price_match(offer.price, price) and _size_match(offer.size_xrp, size):
                unchanged.append(offer.as_dict())
                del target_map[key]
            else:
                to_cancel.append(offer.as_dict())
                del self._open[key]

        now = datetime.now(tz=timezone.utc).isoformat()
        for key, tgt in target_map.items():
            side, level_s = key.split(":", 1)
            placed = VirtualOffer(
                side=side,
                level=int(level_s),
                price=float(tgt["price"]),
                size_xrp=float(tgt.get("size_xrp", 0)),
                placed_at_utc=now,
            )
            self._open[key] = placed
            to_place.append(placed.as_dict())

        if not would_quote:
            summary = (
                f"Dry-run: 0 quotes — cancelled {len(to_cancel)} virtual offer(s); "
                f"open={len(self._open)}"
            )
        elif to_place or to_cancel:
            summary = (
                f"Dry-run: placed {len(to_place)}, cancelled {len(to_cancel)}, "
                f"kept {len(unchanged)} — open {len(self._open)} offer(s) on book"
            )
        else:
            summary = f"Dry-run: no change — {len(unchanged)} offer(s) still open"

        return DryRunOfferDiff(
            would_quote=would_quote,
            to_place=to_place,
            to_cancel=to_cancel,
            unchanged=unchanged,
            open_offers=[o.as_dict() for o in self._open.values()],
            summary=summary,
            cycle=self._cycle,
        )
