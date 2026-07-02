"""Track inventory strength-sell offers until fill or cancel."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass
class StrengthSellRecord:
    sequence: int
    size_xrp: float
    price_rlusd_per_xrp: float
    purpose: str = "strength"  # strength | reload_funding | harvest_trim

    @classmethod
    def from_dict(cls, data: object) -> Optional["StrengthSellRecord"]:
        if not isinstance(data, dict):
            return None
        try:
            seq = int(data.get("sequence", 0))
            if seq <= 0:
                return None
            purpose = str(data.get("purpose") or "strength").strip().lower()
            if purpose not in ("strength", "reload_funding", "harvest_trim"):
                purpose = "strength"
            return cls(
                sequence=seq,
                size_xrp=float(data.get("size_xrp", 0)),
                price_rlusd_per_xrp=float(data.get("price_rlusd_per_xrp", 0)),
                purpose=purpose,
            )
        except (TypeError, ValueError):
            return None


class StrengthSellStore:
    """Persist open strength-sell sequences (non-bracket asks)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._by_seq: Dict[int, StrengthSellRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            rows = data.get("offers", []) if isinstance(data, dict) else []
            for raw in rows:
                rec = StrengthSellRecord.from_dict(raw)
                if rec is not None:
                    self._by_seq[rec.sequence] = rec
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("strength_sell_store_load_failed | %s", exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"offers": [asdict(r) for r in sorted(self._by_seq.values(), key=lambda x: x.sequence)]}
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def register(self, record: StrengthSellRecord) -> None:
        self._by_seq[int(record.sequence)] = record
        self._save()
        logger.info(
            "strength_sell_registered | seq=%s | size=%.4f | price=%.6f",
            record.sequence,
            record.size_xrp,
            record.price_rlusd_per_xrp,
        )

    def remove(self, sequence: int) -> None:
        if int(sequence) in self._by_seq:
            del self._by_seq[int(sequence)]
            self._save()

    def get(self, sequence: int) -> Optional[StrengthSellRecord]:
        return self._by_seq.get(int(sequence))

    def iter_tracked(self) -> Iterator[StrengthSellRecord]:
        yield from self._by_seq.values()
