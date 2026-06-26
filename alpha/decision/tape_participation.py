"""Live-tape participation — waive lagging TA bearish blocks during confirmed uptrends."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from alpha.decision.price_history import PRICE_HISTORY_PATH, load_price_series, normalize_price_source
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TapeParticipationSnapshot:
    active: bool
    reason: str

    def to_dict(self) -> dict:
        return {"active": self.active, "reason": self.reason}


def _short_term_slope_positive(
    *,
    samples: int,
    price_source: str,
    min_lift_pct: float,
) -> bool:
    history = load_price_series(price_source, path=PRICE_HISTORY_PATH)
    n = max(3, int(samples))
    if len(history) < n * 2:
        return False
    recent = history[-n:]
    prior = history[-n * 2 : -n]
    recent_avg = sum(recent) / len(recent)
    prior_avg = sum(prior) / len(prior)
    if prior_avg <= 0:
        return False
    lift = (recent_avg - prior_avg) / prior_avg * 100.0
    return lift >= min_lift_pct


def evaluate_tape_participation(
    config: BotConfig,
    *,
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
) -> TapeParticipationSnapshot:
    """
    True when live book/structure show uptrend participation but closed-bar TA is still bearish.

    Waives hard bearish buy blocks — not score minimums or risk gates.
    """
    if not getattr(config, "alpha_tape_participation_enabled", True):
        return TapeParticipationSnapshot(False, "disabled")

    if mid <= 0 or structure is None:
        return TapeParticipationSnapshot(False, "no_structure")

    if structure.trend == "bearish" or structure.breakout_down:
        return TapeParticipationSnapshot(False, "structure_bearish")

    if ta is None or not ta.enabled:
        return TapeParticipationSnapshot(False, "ta_warming_up")

    min_buy = float(config.alpha_technical_analysis.min_buy_score)
    floor = min_buy * max(0.5, float(getattr(config, "alpha_tape_participation_min_buy_factor", 0.9)))
    if ta.buy_score < floor:
        return TapeParticipationSnapshot(
            False,
            f"buy_score={ta.buy_score:.2f}<{floor:.2f}",
        )

    max_gap = max(0.0, float(getattr(config, "alpha_tape_participation_max_sell_gap", 3.5)))
    if max_gap > 0 and ta.sell_score > ta.buy_score + max_gap:
        return TapeParticipationSnapshot(
            False,
            f"sell_gap={ta.sell_score - ta.buy_score:.2f}>{max_gap:.2f}",
        )

    drift_pct = max(0.0, float(getattr(config, "alpha_tape_uptrend_drift_pct", 0.25)))
    mean = float(structure.mean_mid or 0.0)
    drift_ok = mean > 0 and mid >= mean * (1.0 + drift_pct / 100.0)

    bounce_pct = max(0.0, float(getattr(config, "alpha_tape_bounce_from_low_pct", 0.12)))
    low = float(structure.recent_low or 0.0)
    bounce_ok = low > 0 and mid >= low * (1.0 + bounce_pct / 100.0)

    slope_ok = _short_term_slope_positive(
        samples=int(getattr(config, "alpha_tape_slope_samples", 8)),
        price_source=normalize_price_source(
            str(getattr(config, "alpha_structure_price_source", "ask")),
            default="mid",
        ),
        min_lift_pct=float(getattr(config, "alpha_tape_slope_min_lift_pct", 0.04)),
    )

    tape_up = (
        structure.trend == "bullish"
        or structure.breakout_up
        or drift_ok
        or (slope_ok and bounce_ok)
    )
    if not tape_up:
        return TapeParticipationSnapshot(
            False,
            f"tape_flat drift={drift_ok} slope={slope_ok} bounce={bounce_ok}",
        )

    if ta.bias != "bearish":
        return TapeParticipationSnapshot(False, f"ta_bias={ta.bias}")

    reason = (
        f"uptrend_waiver trend={structure.trend} mid={mid:.6f} mean={mean:.6f} "
        f"buy={ta.buy_score:.2f} sell={ta.sell_score:.2f}"
    )
    logger.info("tape_participation | active | %s", reason)
    return TapeParticipationSnapshot(True, reason)


def tape_participation_waives_bearish_buy_block(
    config: BotConfig,
    *,
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
) -> bool:
    return evaluate_tape_participation(config, mid=mid, structure=structure, ta=ta).active
