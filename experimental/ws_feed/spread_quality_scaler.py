"""
G2 — spread-quality scaler (Phase G / E.2).

Brake-only dimmer from rolling fill markout / toxicity. Never sizes up on hot
streaks, never couples to kill switch, never blocks would_quote.
"""

from __future__ import annotations

from dataclasses import dataclass

G2_VERSION = "1.0.0"
DEFAULT_MIN_FILLS = 8
MAX_SPREAD_MULT = 1.35
MIN_SIZE_MULT = 0.45


@dataclass(frozen=True)
class G2Adjustments:
    """Inputs-only multipliers for pure A-S (size + vol/spread)."""

    size_mult: float = 1.0
    spread_mult: float = 1.0
    grade: str = "neutral"
    active: bool = False
    summary: str = "G2 neutral — no spread-quality brake"
    rationale: str = ""


def compute_g2_adjustments(
    *,
    recent_fills: int = 0,
    toxic_ratio: float = 0.0,
    toxic_ratio_30s: float = 0.0,
    mean_markout_30s_pct: float = 0.0,
    markout_samples_30s: int = 0,
    min_fills: int = DEFAULT_MIN_FILLS,
) -> G2Adjustments:
    """
    Brake-only spread-quality scaler.

  Uses toxicity / markout — not session PnL or inventory MTM. Size mult never
    exceeds 1.0 (no win-chase).
    """
    if recent_fills < 1:
        return G2Adjustments()

    use_30s = markout_samples_30s >= 3
    adverse = toxic_ratio_30s if use_30s else toxic_ratio
    early = recent_fills < min_fills

    size_mult = 1.0
    spread_mult = 1.0
    grade = "neutral"
    rationale = ""

    if adverse >= 0.50 and not early:
        size_mult = 0.55
        spread_mult = 1.25
        grade = "defensive"
        rationale = f"adverse {adverse:.0%} (n={recent_fills})"
    elif adverse >= 0.50 and early:
        size_mult = 0.82
        spread_mult = 1.08
        grade = "cautious"
        rationale = f"early sample adverse {adverse:.0%} ({recent_fills}/{min_fills} fills)"
    elif adverse >= 0.25:
        size_mult = 0.75
        spread_mult = 1.12
        grade = "cautious"
        rationale = f"mixed adverse {adverse:.0%}"
    elif adverse >= 0.18:
        size_mult = 0.65
        spread_mult = 1.15
        grade = "stressed"
        rationale = f"elevated adverse {adverse:.0%}"
    elif mean_markout_30s_pct > 0.08 and adverse < 0.15:
        # Explicit no win-chase: good markout does not size up.
        grade = "ok"
        rationale = (
            f"markout {mean_markout_30s_pct:+.3f}% — G2 holds neutral (no chase)"
        )

    size_mult = max(MIN_SIZE_MULT, min(1.0, size_mult))
    spread_mult = max(1.0, min(MAX_SPREAD_MULT, spread_mult))
    active = size_mult < 1.0 or spread_mult > 1.0

    if active:
        summary = (
            f"G2 {grade}: size×{size_mult:.2f} spread×{spread_mult:.2f} "
            f"({rationale}) — stay on book"
        )
    elif grade == "ok":
        summary = f"G2 ok: {rationale}"
    else:
        summary = "G2 neutral — spread quality acceptable"

    return G2Adjustments(
        size_mult=size_mult,
        spread_mult=spread_mult,
        grade=grade,
        active=active,
        summary=summary,
        rationale=rationale,
    )
