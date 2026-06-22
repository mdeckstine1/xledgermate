"""Persistent bracket registry indexed by offer sequence."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from alpha.orders.types import (
    BracketLeg,
    BracketLegRole,
    BracketLifecycleState,
    BracketMode,
    BracketRecord,
)

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("logs/alpha_brackets.json")


def _leg_to_dict(leg: Optional[BracketLeg]) -> Optional[dict]:
    if leg is None:
        return None
    return {
        "role": leg.role.value,
        "sequence": leg.sequence,
        "price_rlusd_per_xrp": leg.price_rlusd_per_xrp,
        "size_xrp": leg.size_xrp,
        "remaining_xrp": leg.remaining_xrp,
    }


def _leg_from_dict(data: Optional[dict]) -> Optional[BracketLeg]:
    if not data:
        return None
    return BracketLeg(
        role=BracketLegRole(data["role"]),
        sequence=data.get("sequence"),
        price_rlusd_per_xrp=float(data.get("price_rlusd_per_xrp", 0.0)),
        size_xrp=float(data.get("size_xrp", 0.0)),
        remaining_xrp=float(data.get("remaining_xrp", 0.0)),
    )


def _record_to_dict(record: BracketRecord) -> dict:
    return {
        "bracket_id": record.bracket_id,
        "state": record.state.value,
        "mode": record.mode.value,
        "buy_sequence": record.buy_sequence,
        "entry_price_rlusd_per_xrp": record.entry_price_rlusd_per_xrp,
        "target_size_xrp": record.target_size_xrp,
        "filled_xrp": record.filled_xrp,
        "bracketed_xrp": record.bracketed_xrp,
        "tp_leg": _leg_to_dict(record.tp_leg),
        "sl_leg": _leg_to_dict(record.sl_leg),
        "breakeven_passed": record.breakeven_passed,
        "breakout_confirmed": record.breakout_confirmed,
        "peak_mid_rlusd_per_xrp": record.peak_mid_rlusd_per_xrp,
        "last_sl_trail_anchor_mid": record.last_sl_trail_anchor_mid,
        "last_tp_trail_anchor_mid": record.last_tp_trail_anchor_mid,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _record_from_dict(data: dict) -> BracketRecord:
    return BracketRecord(
        bracket_id=str(data["bracket_id"]),
        state=BracketLifecycleState(data["state"]),
        mode=BracketMode(data.get("mode", "bracket")),
        buy_sequence=int(data["buy_sequence"]),
        entry_price_rlusd_per_xrp=float(data["entry_price_rlusd_per_xrp"]),
        target_size_xrp=float(data["target_size_xrp"]),
        filled_xrp=float(data.get("filled_xrp", 0.0)),
        bracketed_xrp=float(data.get("bracketed_xrp", 0.0)),
        tp_leg=_leg_from_dict(data.get("tp_leg")),
        sl_leg=_leg_from_dict(data.get("sl_leg")),
        breakeven_passed=bool(data.get("breakeven_passed", False)),
        breakout_confirmed=bool(data.get("breakout_confirmed", False)),
        peak_mid_rlusd_per_xrp=float(data.get("peak_mid_rlusd_per_xrp", 0.0)),
        last_sl_trail_anchor_mid=float(data.get("last_sl_trail_anchor_mid", 0.0)),
        last_tp_trail_anchor_mid=float(data.get("last_tp_trail_anchor_mid", 0.0)),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )


class BracketStateStore:
    """Tracks bracket pairs by id and offer sequence; optional JSON persistence."""

    def __init__(self, *, persist_path: Optional[Path] = None) -> None:
        self._by_id: Dict[str, BracketRecord] = {}
        self._buy_seq: Dict[int, str] = {}
        self._leg_seq: Dict[int, str] = {}
        self._persist_path = persist_path or _DEFAULT_PATH
        self._load()

    def _rebuild_indexes(self) -> None:
        self._buy_seq.clear()
        self._leg_seq.clear()
        for record in self._by_id.values():
            self._buy_seq[record.buy_sequence] = record.bracket_id
            for leg in (record.tp_leg, record.sl_leg):
                if leg is not None and leg.sequence:
                    self._leg_seq[int(leg.sequence)] = record.bracket_id

    def _load(self) -> None:
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            payload = json.loads(self._persist_path.read_text(encoding="utf-8"))
            records = payload.get("records", [])
            for item in records:
                record = _record_from_dict(item)
                self._by_id[record.bracket_id] = record
            self._rebuild_indexes()
            logger.info("bracket_store_loaded | count=%d", len(self._by_id))
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            logger.warning("bracket_store_load_failed | %s", exc)

    def persist(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [_record_to_dict(r) for r in self._by_id.values()]}
        self._persist_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def all_records(self) -> List[BracketRecord]:
        return list(self._by_id.values())

    def get(self, bracket_id: str) -> Optional[BracketRecord]:
        return self._by_id.get(bracket_id)

    def get_by_buy_sequence(self, sequence: int) -> Optional[BracketRecord]:
        bracket_id = self._buy_seq.get(sequence)
        return self._by_id.get(bracket_id) if bracket_id else None

    def get_by_leg_sequence(self, sequence: int) -> Optional[BracketRecord]:
        bracket_id = self._leg_seq.get(sequence)
        return self._by_id.get(bracket_id) if bracket_id else None

    def add(self, record: BracketRecord) -> None:
        self._by_id[record.bracket_id] = record
        self._buy_seq[record.buy_sequence] = record.bracket_id
        self.persist()

    def register_leg_sequence(self, sequence: int, bracket_id: str) -> None:
        if sequence is not None and sequence > 0:
            self._leg_seq[sequence] = bracket_id
            self.persist()

    def unregister_leg_sequence(self, sequence: Optional[int]) -> None:
        if sequence is not None and sequence in self._leg_seq:
            del self._leg_seq[sequence]
            self.persist()

    def remove(self, bracket_id: str) -> None:
        record = self._by_id.pop(bracket_id, None)
        if record is None:
            return
        self._buy_seq.pop(record.buy_sequence, None)
        for leg in (record.tp_leg, record.sl_leg):
            if leg is not None:
                self.unregister_leg_sequence(leg.sequence)
        self.persist()

    def touch_persist(self) -> None:
        """Persist after in-place record mutations."""
        self.persist()

    def active_bracket_count(self) -> int:
        return sum(
            1
            for r in self._by_id.values()
            if r.state.value in ("pending_buy", "bracket_active", "trailing_placeholder")
        )

    def pending_buy_count(self) -> int:
        return sum(1 for r in self._by_id.values() if r.state.value == "pending_buy")

    def state_labels(self) -> tuple[str, ...]:
        return tuple(f"{r.bracket_id}:{r.state.value}" for r in self._by_id.values())

    def iter_open(self) -> Iterable[BracketRecord]:
        for record in self._by_id.values():
            if record.state.value not in ("tp_filled", "sl_filled", "cancelled"):
                yield record
