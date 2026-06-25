"""Trailing bracket behavior — breakeven SL trail and breakout TP trail."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from alpha.decision.structure import (
    CandleData,
    MarketStructureSnapshot,
    breakout_lookback_samples,
    confirm_breakout,
    recent_swing_high,
)
from alpha.orders.types import BracketLifecycleState, BracketMode, BracketRecord
from alpha.precision import price_decimals, price_eps, round_rlusd_price
from config.settings import BotConfig

logger = logging.getLogger(__name__)

_COMPARE_EPS = 1e-9


@dataclass(frozen=True)
class TrailingEvalResult:
    """Outcome of one trailing evaluation pass for an active bracket."""

    bracket_id: str
    log_mode: str  # fixed_bracket | sl_trailing | breakout_trailing
    breakeven_passed: bool
    breakout_confirmed: bool
    peak_mid_rlusd_per_xrp: float
    new_sl_price: Optional[float] = None
    new_tp_price: Optional[float] = None
    sl_trail_triggered: bool = False
    tp_trail_triggered: bool = False
    mode_changed: bool = False


def is_breakeven_passed(entry_price: float, current_price: float) -> bool:
    """
    Trailing SL activates only after price passes the purchase price.

    For a long-XRP bracket, entry is RLUSD/XRP; breakeven when price >= entry.
    """
    if entry_price <= 0 or current_price <= 0:
        return False
    return current_price >= entry_price - _COMPARE_EPS


def is_breakeven_passed_for_record(record: BracketRecord, mid: float) -> bool:
    """Record-scoped breakeven check."""
    return is_breakeven_passed(record.entry_price_rlusd_per_xrp, mid)


def _update_peak(record: BracketRecord, mid: float) -> float:
    peak = max(record.peak_mid_rlusd_per_xrp, mid, record.entry_price_rlusd_per_xrp)
    record.peak_mid_rlusd_per_xrp = peak
    return peak


def _step_threshold_reached(peak: float, anchor: float, step_pct: float) -> bool:
    if anchor <= 0 or step_pct <= 0:
        return False
    return peak >= anchor * (1.0 + step_pct / 100.0)


def evaluate_trailing_sl(
    record: BracketRecord,
    mid: float,
    config: BotConfig,
) -> Optional[float]:
    """
    Ratchet SL upward after breakeven when peak advances by ``trailing_step_pct``.

    Rules:
    - Only after breakeven (price >= entry)
    - First activation locks SL at entry (breakeven protection)
    - Subsequent moves: max(current SL, entry, peak * (1 - step_pct))
    """
    if not is_breakeven_passed_for_record(record, mid):
        return None
    if record.sl_leg is None:
        return None

    entry = record.entry_price_rlusd_per_xrp
    current_sl = record.sl_leg.price_rlusd_per_xrp
    dec = price_decimals(config)
    eps = price_eps(dec)

    # Initial breakeven lock — SL never below entry once trailing is armed.
    if current_sl < entry - eps:
        peak = _update_peak(record, mid)
        anchor_entry = max(record.last_sl_trail_anchor_mid, entry)
        record.last_sl_trail_anchor_mid = anchor_entry
        step_pct = max(0.0, config.trailing_step_pct)
        if step_pct > 0 and _step_threshold_reached(peak, anchor_entry, step_pct):
            candidate = round_rlusd_price(peak * (1.0 - step_pct / 100.0), dec, direction="down")
            new_sl = max(entry, candidate)
            record.last_sl_trail_anchor_mid = peak
            logger.info(
                "trailing_sl_activated | id=%s | entry=%.6f | peak=%.6f | new_sl=%.6f | stepped=1",
                record.bracket_id,
                entry,
                peak,
                new_sl,
            )
            return new_sl
        logger.info(
            "trailing_sl_activated | id=%s | entry=%.6f | price=%.6f | new_sl=%.6f",
            record.bracket_id,
            entry,
            mid,
            entry,
        )
        return round_rlusd_price(entry, dec, direction="down")

    step_pct = max(0.0, config.trailing_step_pct)
    if step_pct <= 0:
        return None

    peak = _update_peak(record, mid)
    anchor = record.last_sl_trail_anchor_mid
    # Repair: BE gap set anchor to peak while SL stayed at entry — ratchet from entry.
    if anchor > entry + eps and current_sl <= entry + eps:
        anchor = entry
        record.last_sl_trail_anchor_mid = entry
    if anchor <= 0:
        record.last_sl_trail_anchor_mid = peak
        return None

    if not _step_threshold_reached(peak, anchor, step_pct):
        return None

    candidate = round_rlusd_price(peak * (1.0 - step_pct / 100.0), dec, direction="down")
    new_sl = max(current_sl, entry, candidate)
    if new_sl <= current_sl + eps:
        record.last_sl_trail_anchor_mid = peak
        return None

    record.last_sl_trail_anchor_mid = peak
    logger.info(
        "trailing_sl_update | id=%s | peak=%.6f | old_sl=%.6f | new_sl=%.6f | step_pct=%.2f",
        record.bracket_id,
        peak,
        current_sl,
        new_sl,
        step_pct,
    )
    return new_sl


def is_breakout_confirmed(
    record: BracketRecord,
    candle_data: Optional[CandleData],
    structure: Optional[MarketStructureSnapshot],
    config: BotConfig,
    *,
    ta: object | None = None,
) -> bool:
    """
    Breakout confirmation on ``breakout_confirmation_tf`` (spec):

    - Close above recent swing high / key resistance
    - Strong momentum candle (green, large body, close in upper half)
    """
    if record.breakout_confirmed:
        return True
    if not config.bracket_trailing_enabled:
        return False

    candle = candle_data
    swing_high = 0.0
    if structure is not None:
        if candle is None:
            candle = structure.confirmation_candle
        swing_high = structure.swing_high or structure.recent_high

    if candle is None or swing_high <= 0:
        return False

    volume_ok = candle.volume is None or candle.volume > 0
    structure_ok = confirm_breakout(candle, swing_high=swing_high, volume_ok=volume_ok)
    if structure_ok:
        return True
    if config.alpha_technical_analysis.enabled and ta is not None:
        from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot

        if isinstance(ta, TechnicalAnalysisSnapshot) and ta.enabled and ta.breakout_confirmed:
            logger.info(
                "breakout_confirmed_ta | id=%s | breakout_score=%.2f",
                record.bracket_id,
                ta.breakout_score,
            )
            return True
    return False


def evaluate_trailing_tp(
    record: BracketRecord,
    mid: float,
    config: BotConfig,
) -> Optional[float]:
    """
    Ratchet TP upward after breakout when peak advances by ``trailing_step_pct``.

    TP remains fixed until ``record.breakout_confirmed``; then trails higher.
    """
    if not record.breakout_confirmed:
        return None
    if record.tp_leg is None:
        return None

    step_pct = max(0.0, config.trailing_step_pct)
    if step_pct <= 0:
        return None

    peak = _update_peak(record, mid)
    anchor = record.last_tp_trail_anchor_mid
    if anchor <= 0:
        record.last_tp_trail_anchor_mid = peak
        return None

    if not _step_threshold_reached(peak, anchor, step_pct):
        return None

    current_tp = record.tp_leg.price_rlusd_per_xrp
    dec = price_decimals(config)
    eps = price_eps(dec)
    candidate = round_rlusd_price(peak * (1.0 + step_pct / 100.0), dec, direction="up")
    new_tp = max(current_tp, candidate)
    if new_tp <= current_tp + eps:
        record.last_tp_trail_anchor_mid = peak
        return None

    record.last_tp_trail_anchor_mid = peak
    logger.info(
        "trailing_tp_update | id=%s | peak=%.6f | old_tp=%.6f | new_tp=%.6f | step_pct=%.2f",
        record.bracket_id,
        peak,
        current_tp,
        new_tp,
        step_pct,
    )
    return new_tp


def _resolve_market_context(
    current_price: float,
    candle_data: Optional[CandleData],
    structure: Optional[MarketStructureSnapshot],
) -> tuple[float, Optional[CandleData], Optional[MarketStructureSnapshot]]:
    """Prefer explicit price/candle; fall back to structure snapshot."""
    mid = current_price if current_price > 0 else 0.0
    if structure is not None and structure.mid > 0:
        mid = structure.mid if mid <= 0 else mid

    candle = candle_data
    if candle is None and structure is not None:
        candle = structure.confirmation_candle

    if structure is None and mid > 0:
        swing = 0.0
        if candle is not None:
            swing = recent_swing_high(
                [candle.open, candle.high, candle.low, candle.close],
                exclude_last=True,
            )
        structure = MarketStructureSnapshot(
            mid=mid,
            sample_count=1,
            mean_mid=mid,
            recent_high=candle.high if candle else mid,
            recent_low=candle.low if candle else mid,
            trend="neutral",
            breakout_up=False,
            breakout_down=False,
            summary="synthetic_trailing_context",
            swing_high=swing or (candle.high if candle else mid),
            confirmation_candle=candle,
        )

    return mid, candle, structure


def evaluate_trailing(
    record: BracketRecord,
    config: BotConfig,
    *,
    current_price: float = 0.0,
    candle_data: Optional[CandleData] = None,
    structure: Optional[MarketStructureSnapshot] = None,
    ta: object | None = None,
) -> TrailingEvalResult:
    """
    Full trailing evaluation for one active bracket.

    Updates trailing flags in place; returns new SL/TP prices to apply on ledger.
    """
    empty = TrailingEvalResult(
        bracket_id=record.bracket_id,
        log_mode="fixed_bracket",
        breakeven_passed=record.breakeven_passed,
        breakout_confirmed=record.breakout_confirmed,
        peak_mid_rlusd_per_xrp=record.peak_mid_rlusd_per_xrp,
    )

    if not config.bracket_trailing_enabled:
        return empty
    if record.state != BracketLifecycleState.BRACKET_ACTIVE:
        return empty

    mid, candle, snap = _resolve_market_context(current_price, candle_data, structure)
    if mid <= 0:
        return empty

    mode_changed = False

    if is_breakeven_passed_for_record(record, mid) and not record.breakeven_passed:
        record.breakeven_passed = True
        record.last_sl_trail_anchor_mid = record.entry_price_rlusd_per_xrp
        logger.info(
            "bracket_breakeven_passed | id=%s | entry=%.6f | mid=%.6f",
            record.bracket_id,
            record.entry_price_rlusd_per_xrp,
            mid,
        )

    _update_peak(record, mid)

    if is_breakout_confirmed(record, candle, snap, config, ta=ta) and not record.breakout_confirmed:
        record.breakout_confirmed = True
        record.mode = BracketMode.BREAKOUT_TRAILING
        if record.last_tp_trail_anchor_mid <= 0:
            record.last_tp_trail_anchor_mid = max(
                record.tp_leg.price_rlusd_per_xrp if record.tp_leg else 0.0,
                record.peak_mid_rlusd_per_xrp,
            )
        mode_changed = True
        logger.info(
            "trailing_tp_enabled | id=%s | entry=%.6f | mid=%.6f | tf=%s",
            record.bracket_id,
            record.entry_price_rlusd_per_xrp,
            mid,
            config.breakout_confirmation_tf,
        )

    new_sl = evaluate_trailing_sl(record, mid, config) if record.breakeven_passed else None
    new_tp = evaluate_trailing_tp(record, mid, config) if record.breakout_confirmed else None

    sl_triggered = new_sl is not None
    tp_triggered = new_tp is not None

    if record.breakout_confirmed:
        log_mode = "breakout_trailing"
    elif record.breakeven_passed:
        log_mode = "sl_trailing"
    else:
        log_mode = "fixed_bracket"

    if sl_triggered or tp_triggered or mode_changed:
        record.touch()

    return TrailingEvalResult(
        bracket_id=record.bracket_id,
        log_mode=log_mode,
        breakeven_passed=record.breakeven_passed,
        breakout_confirmed=record.breakout_confirmed,
        peak_mid_rlusd_per_xrp=record.peak_mid_rlusd_per_xrp,
        new_sl_price=new_sl,
        new_tp_price=new_tp,
        sl_trail_triggered=sl_triggered,
        tp_trail_triggered=tp_triggered,
        mode_changed=mode_changed,
    )
