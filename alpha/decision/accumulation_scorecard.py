"""Accumulation scorecard — did we deploy RLUSD on rips?"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot


def divergence_snapshot_from_ta(ta: Optional["TechnicalAnalysisSnapshot"]) -> Dict[str, Any]:
    if ta is None:
        return {}
    return {
        "fired": bool(getattr(ta, "divergence_fired", False)),
        "bias": getattr(ta, "divergence_bias", "neutral") or "neutral",
        "kind": getattr(ta, "divergence_kind", "") or "",
        "indicator": getattr(ta, "divergence_indicator", "") or "",
        "strength": round(float(getattr(ta, "divergence_strength", 0.0) or 0.0), 3),
        "detail": getattr(ta, "divergence_detail", "") or "",
    }


def merge_ta_divergence_into_scorecard(
    scorecard: Dict[str, Any],
    ta: Optional["TechnicalAnalysisSnapshot"],
) -> Dict[str, Any]:
    out = dict(scorecard)
    div = divergence_snapshot_from_ta(ta)
    if div:
        out["divergence"] = div
    return out


def build_accumulation_scorecard_block(scorecard: Dict[str, Any]) -> str:
    if not scorecard:
        return "=== Accumulation scorecard ===\n(not tracked)"
    missed = scorecard.get("missed_opportunity")
    flag = "YES — tape up while idle/blocked" if missed else "no"
    lines = [
        "=== Accumulation scorecard (fills matter — not place_bid alone) ===",
        f"bids_placed={scorecard.get('bids_placed')} fills={scorecard.get('fills_count')} "
        f"chase_cancels={scorecard.get('chase_cancels')} fill_rate={scorecard.get('fill_rate_pct')}%",
        f"rlusd_filled={scorecard.get('rlusd_filled_rlusd')} committed={scorecard.get('rlusd_committed_rlusd')}",
        f"phase_minutes={scorecard.get('phase_minutes')}",
        f"window_mid_move_pct={scorecard.get('window_mid_move_pct')} missed_opportunity={flag}",
        f"headline={scorecard.get('headline')}",
    ]
    div = scorecard.get("divergence") or {}
    if div.get("fired"):
        lines.append(
            f"divergence={div.get('kind')} ({div.get('indicator')}) "
            f"strength={div.get('strength')} bias={div.get('bias')} — {div.get('detail', '')}"
        )
    return "\n".join(lines)
