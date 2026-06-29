"""Accumulation scorecard — did we deploy RLUSD on rips?"""

from __future__ import annotations

from typing import Any, Dict


def build_accumulation_scorecard_block(scorecard: Dict[str, Any]) -> str:
    if not scorecard:
        return "=== Accumulation scorecard ===\n(not tracked)"
    missed = scorecard.get("missed_opportunity")
    flag = "YES — tape up while idle/blocked" if missed else "no"
    return "\n".join(
        [
            "=== Accumulation scorecard (fills matter — not place_bid alone) ===",
            f"bids_placed={scorecard.get('bids_placed')} fills={scorecard.get('fills_count')} "
            f"chase_cancels={scorecard.get('chase_cancels')} fill_rate={scorecard.get('fill_rate_pct')}%",
            f"rlusd_filled={scorecard.get('rlusd_filled_rlusd')} committed={scorecard.get('rlusd_committed_rlusd')}",
            f"phase_minutes={scorecard.get('phase_minutes')}",
            f"window_mid_move_pct={scorecard.get('window_mid_move_pct')} missed_opportunity={flag}",
            f"headline={scorecard.get('headline')}",
        ]
    )
