"""Tests for Trading Bot Alpha trailing SL/TP logic."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from alpha.decision.structure import (
    CandleData,
    MarketStructureSnapshot,
    analyze_structure,
    breakout_lookback_samples,
    confirm_breakout,
)
from alpha.dry_run import DryRunGuard
from alpha.orders.manager import OrderManager
from alpha.orders.state import BracketStateStore
from alpha.orders.trailing import (
    TrailingEvalResult,
    evaluate_trailing,
    evaluate_trailing_sl,
    evaluate_trailing_tp,
    is_breakeven_passed,
    is_breakeven_passed_for_record,
    is_breakout_confirmed,
)
from alpha.orders.types import (
    BracketLeg,
    BracketLegRole,
    BracketLifecycleState,
    BracketMode,
    BracketRecord,
)
from alpha.types import LedgerOfferResult
from config.settings import BotConfig


def _trailing_config(**overrides: Any) -> BotConfig:
    base = BotConfig(
        dry_run=True,
        bracket_trailing_enabled=True,
        trailing_step_pct=1.0,
        breakout_confirmation_tf="15m",
        alpha_cycle_interval_seconds=60,
        alpha_breakout_pct=0.02,
        initial_stop_loss_pct=0.02,
        take_profit_rr=2.0,
        min_order_size_xrp=1.0,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _active_record(
    *,
    entry: float = 2.0,
    sl: float = 1.96,
    tp: float = 2.08,
) -> BracketRecord:
    return BracketRecord(
        bracket_id="trail-test",
        state=BracketLifecycleState.BRACKET_ACTIVE,
        mode=BracketMode.BRACKET,
        buy_sequence=1,
        entry_price_rlusd_per_xrp=entry,
        target_size_xrp=10.0,
        filled_xrp=10.0,
        bracketed_xrp=10.0,
        sl_leg=BracketLeg(
            role=BracketLegRole.STOP_LOSS,
            sequence=100,
            price_rlusd_per_xrp=sl,
            size_xrp=10.0,
            remaining_xrp=10.0,
        ),
        tp_leg=BracketLeg(
            role=BracketLegRole.TAKE_PROFIT,
            sequence=101,
            price_rlusd_per_xrp=tp,
            size_xrp=10.0,
            remaining_xrp=10.0,
        ),
    )


def _structure(
    mid: float,
    *,
    swing_high: float = 2.0,
    candle: Optional[CandleData] = None,
) -> MarketStructureSnapshot:
    return MarketStructureSnapshot(
        mid=mid,
        sample_count=20,
        mean_mid=mid * 0.99,
        recent_high=mid,
        recent_low=mid * 0.98,
        trend="bullish",
        breakout_up=False,
        breakout_down=False,
        summary="test",
        swing_high=swing_high,
        confirmation_candle=candle,
    )


def test_is_breakeven_passed():
    record = _active_record(entry=2.0)
    assert not is_breakeven_passed(2.0, 1.99)
    assert is_breakeven_passed(2.0, 2.0)
    assert is_breakeven_passed_for_record(record, 2.05)


def test_breakout_lookback_samples():
    assert breakout_lookback_samples("15m", 60) == 15
    assert breakout_lookback_samples("1h", 60) == 60
    assert breakout_lookback_samples("30", 60) == 30


def test_evaluate_trailing_sl_ratchets_after_step():
    cfg = _trailing_config(trailing_step_pct=1.0)
    record = _active_record(entry=2.0, sl=1.96)
    record.breakeven_passed = True
    record.last_sl_trail_anchor_mid = 2.0

    locked = evaluate_trailing_sl(record, 2.0, cfg)
    assert locked == 2.0
    assert record.sl_leg is not None
    record.sl_leg.price_rlusd_per_xrp = 2.0

    assert evaluate_trailing_sl(record, 2.01, cfg) is None

    new_sl = evaluate_trailing_sl(record, 2.03, cfg)
    assert new_sl is not None
    assert new_sl >= 2.0
    assert new_sl == round(2.03 * 0.99, 6)


def test_evaluate_trailing_tp_only_after_breakout():
    cfg = _trailing_config(trailing_step_pct=1.0)
    record = _active_record(tp=2.08)
    assert evaluate_trailing_tp(record, 2.10, cfg) is None

    record.breakout_confirmed = True
    record.last_tp_trail_anchor_mid = 2.08
    new_tp = evaluate_trailing_tp(record, 2.12, cfg)
    assert new_tp is not None
    assert new_tp > 2.08
    assert new_tp == round(2.12 * 1.01, 6)


def test_is_breakout_confirmed_requires_momentum_candle():
    cfg = _trailing_config()
    record = _active_record()
    below_swing = CandleData(open=2.0, high=2.01, low=1.99, close=1.995)
    structure = _structure(1.995, swing_high=2.0, candle=below_swing)
    assert not is_breakout_confirmed(record, below_swing, structure, cfg)

    weak = CandleData(open=2.01, high=2.02, low=1.99, close=2.005)
    structure_weak = _structure(2.005, swing_high=2.0, candle=weak)
    assert not confirm_breakout(weak, swing_high=2.0)
    assert not is_breakout_confirmed(record, weak, structure_weak, cfg)

    strong = CandleData(open=2.0, high=2.05, low=1.99, close=2.04)
    structure_ok = _structure(2.04, swing_high=2.0, candle=strong)
    assert confirm_breakout(strong, swing_high=2.0)
    assert is_breakout_confirmed(record, strong, structure_ok, cfg)


def test_evaluate_trailing_full_flow():
    cfg = _trailing_config(trailing_step_pct=1.0)
    record = _active_record(entry=2.0, sl=1.96, tp=2.08)

    pre_be = _structure(1.99, swing_high=2.0)
    r1 = evaluate_trailing(record, cfg, current_price=1.99, structure=pre_be)
    assert isinstance(r1, TrailingEvalResult)
    assert not r1.breakeven_passed
    assert not r1.breakout_confirmed

    at_be = _structure(2.0, swing_high=2.0)
    r2 = evaluate_trailing(record, cfg, current_price=2.0, structure=at_be)
    assert r2.breakeven_passed
    assert not r2.breakout_confirmed

    strong = CandleData(open=2.0, high=2.06, low=1.99, close=2.05)
    breakout = _structure(2.05, swing_high=2.0, candle=strong)
    record.last_sl_trail_anchor_mid = 2.0
    record.peak_mid_rlusd_per_xrp = 2.05
    record.sl_leg.price_rlusd_per_xrp = 2.0
    r3 = evaluate_trailing(
        record,
        cfg,
        current_price=2.05,
        candle_data=strong,
        structure=breakout,
    )
    assert r3.breakout_confirmed
    assert record.mode == BracketMode.BREAKOUT_TRAILING
    assert record.state == BracketLifecycleState.BRACKET_ACTIVE


def test_bracket_store_trailing_fields_roundtrip(tmp_path: Path):
    path = tmp_path / "brackets.json"
    store = BracketStateStore(persist_path=path)
    record = _active_record()
    record.breakeven_passed = True
    record.peak_mid_rlusd_per_xrp = 2.05
    record.last_sl_trail_anchor_mid = 2.0
    store.add(record)

    loaded = BracketStateStore(persist_path=path).get("trail-test")
    assert loaded is not None
    assert loaded.breakeven_passed is True
    assert loaded.peak_mid_rlusd_per_xrp == 2.05
    assert loaded.last_sl_trail_anchor_mid == 2.0


class _TrailFakeLedger:
    def __init__(self) -> None:
        self._offers: Dict[int, dict[str, Any]] = {}
        self._next_seq = 2000
        self.cancelled: List[int] = []
        self.placed: List[tuple[float, float]] = []

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return list(self._offers.values())

    async def place_limit_sell_xrp(self, *, size_xrp: float, price_rlusd_per_xrp: float) -> LedgerOfferResult:
        self._next_seq += 1
        seq = self._next_seq
        self._offers[seq] = {
            "sequence": seq,
            "side": "ask",
            "price": price_rlusd_per_xrp,
            "size_xrp": size_xrp,
        }
        self.placed.append((size_xrp, price_rlusd_per_xrp))
        return LedgerOfferResult(submitted=True, dry_run=False, action="sell", sequence=seq)

    async def cancel_offer(self, sequence: int) -> LedgerOfferResult:
        self.cancelled.append(sequence)
        self._offers.pop(sequence, None)
        return LedgerOfferResult(submitted=True, dry_run=False, action="cancel", sequence=sequence)


def test_order_manager_trailing_dry_run_updates_sl_price():
    async def _run() -> None:
        ledger = _TrailFakeLedger()
        ledger._offers[100] = {"sequence": 100, "side": "ask", "price": 1.96, "size_xrp": 10.0}
        ledger._offers[101] = {"sequence": 101, "side": "ask", "price": 2.08, "size_xrp": 10.0}

        cfg = _trailing_config(trailing_step_pct=1.0)
        mgr = OrderManager(ledger, DryRunGuard(dry_run=True, network="mainnet"), cfg)

        record = _active_record(entry=2.0, sl=2.0)
        record.breakeven_passed = True
        record.last_sl_trail_anchor_mid = 2.0
        record.peak_mid_rlusd_per_xrp = 2.0
        mgr.store._by_id[record.bracket_id] = record

        strong = CandleData(open=2.0, high=2.06, low=1.99, close=2.05)
        structure = _structure(2.03, swing_high=2.0, candle=strong)
        mgr.set_structure(structure)

        updates = await mgr.update_trailing_orders(2.03, structure.confirmation_candle, structure=structure)
        assert updates >= 1
        assert record.sl_leg is not None
        assert record.sl_leg.price_rlusd_per_xrp > 2.0
        assert len(ledger.cancelled) == 0

    asyncio.run(_run())


def test_analyze_structure_includes_confirmation_candle(tmp_path: Path):
    hist = tmp_path / "mid_history.json"
    for mid in [2.0, 2.01, 2.02, 2.03, 2.04]:
        analyze_structure(
            mid,
            breakout_pct=0.5,
            lookback=5,
            breakout_tf="5m",
            cycle_seconds=60,
            path=hist,
        )
    snap = analyze_structure(
        2.05,
        breakout_pct=0.5,
        lookback=5,
        breakout_tf="5m",
        cycle_seconds=60,
        path=hist,
    )
    assert snap.confirmation_candle is not None
    assert snap.swing_high > 0
