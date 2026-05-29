"""Market condition assessment and profile recommendation for defensive MM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.perception import BUILT_IN_PROFILES, Profile

# Condition tiers (defensive bot: default conservative).
CONDITION_FAVORABLE = "favorable"
CONDITION_NEUTRAL = "neutral"
CONDITION_DEFENSIVE = "defensive"
CONDITION_HOSTILE = "hostile"

CONDITION_LABELS = {
    CONDITION_FAVORABLE: "Favorable",
    CONDITION_NEUTRAL: "Neutral",
    CONDITION_DEFENSIVE: "Defensive",
    CONDITION_HOSTILE: "Hostile",
}


@dataclass(frozen=True)
class MarketAssessment:
    """Snapshot of book + volatility health used for quoting and GUI."""

    condition: str
    condition_label: str
    volatility_pct: float
    volatility_level: str
    liquidity_score: float
    liquidity_level: str
    book_spread_pct: float
    book_spread_status: str
    health_score: float
    recommended_profile: str
    recommendation_reason: str
    summary: str


def compute_book_spread_pct(
    best_bid: Optional[float],
    best_ask: Optional[float],
) -> float:
    if best_bid is None or best_ask is None or best_ask <= 0:
        return 0.0
    return max(0.0, ((best_ask - best_bid) / best_ask) * 100.0)


def _level(value: float, *, low: float, high: float) -> str:
    if value <= low:
        return "low"
    if value >= high:
        return "high"
    return "moderate"


def _book_spread_status(spread_pct: float) -> str:
    if spread_pct <= 0:
        return "unknown"
    if spread_pct < 0.15:
        return "tight"
    if spread_pct < 0.45:
        return "normal"
    if spread_pct < 1.0:
        return "wide"
    return "very wide"


def recommend_profile(
    *,
    condition: str,
    volatility_level: str,
    liquidity_level: str,
    book_spread_status: str,
) -> Tuple[str, str]:
    """Suggest profile; user applies manually unless auto-switch is on."""
    if condition == CONDITION_HOSTILE:
        return "safe", "Hostile conditions — use Safe until volatility and liquidity improve."
    if condition == CONDITION_DEFENSIVE:
        if volatility_level == "high":
            return "high_volatility", "Elevated volatility — High volatility profile widens protection."
        if liquidity_level == "low":
            return "thin_liquidity", "Thin book — Thin liquidity profile reduces adverse selection risk."
        return "safe", "Mixed stress — Safe is the default defensive posture."
    if condition == CONDITION_FAVORABLE:
        if liquidity_level == "low":
            return "thin_liquidity", "Liquidity still thin despite stable vol — stay protective."
        return "tight_spread", "Stable vol and decent liquidity — Tight spread can compete for edge."
    # neutral
    if volatility_level == "high":
        return "high_volatility", "Moderate overall but volatility elevated."
    if liquidity_level == "low":
        return "thin_liquidity", "Moderate overall but book depth is weak."
    return "safe", "Balanced conditions — Safe is a sensible default."


def assess_market_conditions(
    *,
    volatility_pct: float,
    liquidity_score: float,
    book_spread_pct: float,
    active_profile: str,
) -> MarketAssessment:
    vol_level = _level(volatility_pct, low=0.08, high=0.35)
    liq_level = _level(liquidity_score, low=0.25, high=0.55)
    spread_status = _book_spread_status(book_spread_pct)

    # Health score 0–100 (higher = better for competitive quoting).
    vol_penalty = min(40.0, volatility_pct * 80.0)
    liq_bonus = liquidity_score * 35.0
    spread_penalty = min(25.0, max(0.0, book_spread_pct - 0.2) * 15.0)
    health = max(0.0, min(100.0, 55.0 + liq_bonus - vol_penalty - spread_penalty))

    if health >= 72 and vol_level != "high" and liq_level != "low":
        condition = CONDITION_FAVORABLE
    elif health >= 48 and vol_level != "high":
        condition = CONDITION_NEUTRAL
    elif health >= 28 or vol_level == "high" or liq_level == "low":
        condition = CONDITION_DEFENSIVE
    else:
        condition = CONDITION_HOSTILE

    if vol_level == "high" and liq_level == "low":
        condition = CONDITION_HOSTILE

    recommended, reason = recommend_profile(
        condition=condition,
        volatility_level=vol_level,
        liquidity_level=liq_level,
        book_spread_status=spread_status,
    )

    summary = (
        f"Market {CONDITION_LABELS[condition].lower()} | vol {vol_level} ({volatility_pct:.2f}%) | "
        f"liq {liq_level} ({liquidity_score:.2f}) | book spread {spread_status} "
        f"({book_spread_pct:.3f}%) | health {health:.0f}/100"
    )

    return MarketAssessment(
        condition=condition,
        condition_label=CONDITION_LABELS[condition],
        volatility_pct=volatility_pct,
        volatility_level=vol_level,
        liquidity_score=liquidity_score,
        liquidity_level=liq_level,
        book_spread_pct=book_spread_pct,
        book_spread_status=spread_status,
        health_score=health,
        recommended_profile=recommended,
        recommendation_reason=reason,
        summary=summary,
    )


def defensive_profile_for_auto_switch(assessment: MarketAssessment) -> Optional[str]:
    """
    Auto-switch only moves toward more defensive profiles — never to tight_spread.
    Returns None if no switch needed.
    """
    current = assessment.recommended_profile
    if current == "tight_spread":
        return None
    return current


def is_more_defensive_than(current: str, proposed: str) -> bool:
    """True if proposed is more defensive than current (for auto-switch guard)."""
    order = {"tight_spread": 0, "safe": 1, "thin_liquidity": 2, "high_volatility": 3}
    return order.get(proposed, 1) > order.get(current, 1)


def profile_display_name(name: str) -> str:
    labels = {
        "safe": "Safe",
        "high_volatility": "High volatility",
        "thin_liquidity": "Thin liquidity",
        "tight_spread": "Tight spread",
    }
    return labels.get(name, name)
