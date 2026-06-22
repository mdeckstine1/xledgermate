"""Phase 6 tests — structure, controls, persistence, GUI helpers."""

from __future__ import annotations

from pathlib import Path

from alpha.decision.structure import analyze_structure, breakout_confirmed_for_long
from alpha.operator.activity import ActivityLog
from alpha.operator.controls import OperatorControlStore
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState, BracketMode, BracketRecord


def test_operator_pause_resume(tmp_path: Path):
    store = OperatorControlStore(path=tmp_path / "controls.json")
    assert not store.is_paused()
    store.pause("test")
    assert store.is_paused()
    store.resume()
    assert not store.is_paused()


def test_activity_log_tail(tmp_path: Path):
    log = ActivityLog(path=tmp_path / "activity.jsonl")
    log.append("test_event", foo="bar")
    rows = log.tail(5)
    assert len(rows) == 1
    assert rows[0]["event"] == "test_event"


def test_bracket_store_persistence_roundtrip(tmp_path: Path):
    path = tmp_path / "brackets.json"
    store = BracketStateStore(persist_path=path)
    record = BracketRecord(
        bracket_id="test-bracket",
        state=BracketLifecycleState.PENDING_BUY,
        mode=BracketMode.BRACKET,
        buy_sequence=42,
        entry_price_rlusd_per_xrp=2.0,
        target_size_xrp=10.0,
    )
    store.add(record)
    store2 = BracketStateStore(persist_path=path)
    loaded = store2.get("test-bracket")
    assert loaded is not None
    assert loaded.buy_sequence == 42


def test_structure_breakout_detection(tmp_path: Path):
    hist = tmp_path / "mid_history.json"
    for mid in [2.0, 2.01, 2.02, 2.03, 2.04]:
        analyze_structure(mid, breakout_pct=0.5, lookback=5, path=hist)
    snap = analyze_structure(2.08, breakout_pct=0.5, lookback=5, path=hist)
    assert snap.trend in ("bullish", "neutral")
    assert breakout_confirmed_for_long(snap, entry_price=2.0, min_breakout_pct=0.5)
