"""
G7 — execution envelope (per-side touch backoff × G2 spread brake).

Execution-only: adjusts posted bid/ask distance from touch. Never changes
reservation, optimal spread, or would_quote.
"""

from __future__ import annotations

from dataclasses import dataclass

G7_VERSION = "1.0.0"
JOIN_BACKOFF_BPS = 3.0
PASSIVE_BACKOFF_BPS = 8.0
INVENTORY_SKEW_THRESHOLD = 0.12


@dataclass(frozen=True)
class ExecutionEnvelope:
    bid_touch_backoff_bps: float
    ask_touch_backoff_bps: float
    g2_spread_mult: float = 1.0
    inventory_posture: str = "balanced"
    bid_role: str = "passive"
    ask_role: str = "passive"
    summary: str = ""
    scaler_label: str = ""

    @property
    def g7_summary(self) -> str:
        return self.summary


def _inventory_posture(*, inventory_label: str, inventory_skew: float) -> str:
    label = (inventory_label or "").lower()
    if inventory_skew > INVENTORY_SKEW_THRESHOLD:
        return "xrp_heavy"
    if inventory_skew < -INVENTORY_SKEW_THRESHOLD:
        return "rlusd_heavy"
    if "rlusd_heavy" in label:
        return "rlusd_heavy"
    if "xrp_heavy" in label:
        return "xrp_heavy"
    return "balanced"


def compute_execution_envelope(
    *,
    inventory_label: str = "",
    inventory_skew: float = 0.0,
    g2_spread_mult: float = 1.0,
) -> ExecutionEnvelope:
    """
  Rule A: per-side base backoff from inventory.
  Rule B: multiply both sides by max(1, g2.spread_mult).
    """
    posture = _inventory_posture(inventory_label=inventory_label, inventory_skew=inventory_skew)
    if posture == "xrp_heavy":
        bid_base, ask_base = PASSIVE_BACKOFF_BPS, JOIN_BACKOFF_BPS
        bid_role, ask_role = "passive", "join"
    elif posture == "rlusd_heavy":
        bid_base, ask_base = JOIN_BACKOFF_BPS, PASSIVE_BACKOFF_BPS
        bid_role, ask_role = "join", "passive"
    else:
        bid_base = ask_base = PASSIVE_BACKOFF_BPS
        bid_role = ask_role = "wide"

    mult = max(1.0, float(g2_spread_mult))
    bid_bps = round(bid_base * mult, 2)
    ask_bps = round(ask_base * mult, 2)

    mult_note = f" × G2 {mult:.2f}" if mult > 1.0 else ""
    summary = f"G7 {posture}: bid {bid_bps:.1f}bps ({bid_role}) · ask {ask_bps:.1f}bps ({ask_role}){mult_note}"
    scaler_label = f"bid {bid_role} {bid_bps:.1f}bps · ask {ask_role} {ask_bps:.1f}bps"

    return ExecutionEnvelope(
        bid_touch_backoff_bps=bid_bps,
        ask_touch_backoff_bps=ask_bps,
        g2_spread_mult=mult,
        inventory_posture=posture,
        bid_role=bid_role,
        ask_role=ask_role,
        summary=summary,
        scaler_label=scaler_label,
    )


def touch_prices_from_backoff(
    *,
    best_bid: float,
    best_ask: float,
    bid_backoff_bps: float,
    ask_backoff_bps: float,
) -> tuple[float, float]:
    """Posted L1 prices from touch backoff (never cross touch)."""
    if best_bid <= 0 or best_ask <= 0:
        return best_bid, best_ask
    bid_post = best_bid * (1.0 - bid_backoff_bps / 10_000.0)
    ask_post = best_ask * (1.0 + ask_backoff_bps / 10_000.0)
    bid_post = min(bid_post, best_bid)
    ask_post = max(ask_post, best_ask)
    return bid_post, ask_post
