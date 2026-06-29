"""Momentum entry — bull-run / breakout bids when inventory is no longer RLUSD-heavy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from alpha.decision.price_history import PRICE_HISTORY_PATH, load_price_series, normalize_price_source
from alpha.decision.tape_participation import (
    _short_term_slope_positive,
    evaluate_tape_participation,
)
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
    from alpha.types import InventorySnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MomentumEntrySnapshot:
    active: bool
    mode: str  # weakness | bull_run | ""
    reason: str

    def to_dict(self) -> dict:
        return {"active": self.active, "mode": self.mode, "reason": self.reason}


def evaluate_bull_run_entry(
    config: BotConfig,
    *,
    inventory: "InventorySnapshot",
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
) -> MomentumEntrySnapshot:
    """
  Allow limit bids during breakouts / bull tape even when deviation is only mildly RLUSD-heavy
  or balanced — the gap the dip-only weakness gate leaves on runs.
  """
    if not getattr(config, "alpha_bull_run_enabled", True):
        return MomentumEntrySnapshot(False, "", "disabled")

    if inventory.pause_bids or inventory.buy_blocked_imbalance:
        return MomentumEntrySnapshot(False, "", "inventory_blocked")

    weakness = float(config.alpha_weakness_deviation)
    if inventory.deviation <= -weakness:
        return MomentumEntrySnapshot(False, "", "weakness_path")

    max_dev = float(getattr(config, "alpha_bull_run_max_deviation", 0.02))
    if inventory.deviation > max_dev:
        return MomentumEntrySnapshot(
            False,
            "",
            f"dev={inventory.deviation:+.3f}>bull_max={max_dev:+.3f}",
        )

    if structure is None or mid <= 0:
        return MomentumEntrySnapshot(False, "", "no_structure")

    if structure.trend == "bearish" or structure.breakout_down:
        return MomentumEntrySnapshot(False, "", "structure_bearish")

    signals: list[str] = []
    if structure.breakout_up:
        signals.append("breakout_up")
    if structure.trend == "bullish":
        signals.append("trend_bullish")
    near_high_pct = max(0.0, float(getattr(config, "alpha_bull_run_near_high_pct", 0.06)))
    if structure.recent_high > 0 and mid >= structure.recent_high * (1.0 - near_high_pct / 100.0):
        slope_ok = _short_term_slope_positive(
            samples=int(getattr(config, "alpha_tape_slope_samples", 8)),
            price_source=normalize_price_source(
                str(getattr(config, "alpha_structure_price_source", "ask")),
                default="mid",
            ),
            min_lift_pct=float(getattr(config, "alpha_tape_slope_min_lift_pct", 0.04)),
        )
        if slope_ok:
            signals.append("near_high_break")
    if ta is not None and ta.enabled:
        if ta.breakout_confirmed:
            signals.append("ta_breakout")
        if ta.bias == "bullish" and ta.buy_score >= config.alpha_technical_analysis.min_buy_score:
            signals.append("ta_bullish")

    tape = evaluate_tape_participation(config, mid=mid, structure=structure, ta=ta)
    if tape.active:
        signals.append("tape_participation")

    if not signals:
        return MomentumEntrySnapshot(False, "", "no_momentum_signal")

    reason = f"bull_run {'+'.join(signals)} dev={inventory.deviation:+.3f}"
    logger.info("momentum_entry | bull_run | %s", reason)
    return MomentumEntrySnapshot(True, "bull_run", reason)


def bull_run_buy_offset_pct(config: BotConfig) -> float:
    chase = float(getattr(config, "alpha_bull_run_buy_offset_pct", 0.0))
    if chase > 0:
        return chase
    base = float(config.alpha_buy_limit_offset_pct or config.alpha_bid_offset_pct or 0.15)
    return min(base, 0.12)
