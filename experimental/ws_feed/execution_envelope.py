"""
G7 — execution envelope (per-side touch backoff × G2 spread brake).

Execution-only: adjusts posted bid/ask distance from touch. Never changes
reservation, optimal spread, or would_quote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

G7_VERSION = "1.5.0"
JOIN_BACKOFF_BPS = 5.0
SOLO_JOIN_BACKOFF_BPS = 3.0
PASSIVE_BACKOFF_BPS = 8.0
INVENTORY_SKEW_THRESHOLD = 0.12
JOIN_HALF_SPREAD_FRAC = 0.45
# A1 — widen ask when SELL-side bleed signals fire (execution only).
ASK_DEFENSE_EXTRA_BPS = 2.0
SELL_DEFENSE_TOXIC_30S = 0.15
SELL_DEFENSE_MARKOUT_PCT = -0.005
SELL_DEFENSE_MIN_FILLS = 8
# A2 — solo empty peer lane.
SOLO_ACQUIRE_TOXIC_30S_MAX = 0.20
# Inventory acquire: bid join can stay tight when toxic is from SELL fills (G2 brake).
SOLO_BID_TOXIC_MAX = 0.35
ACCUMULATE_POSTURES = frozenset({"balanced", "rlusd_heavy", "slight_rlusd_heavy"})
HOLD_XRP_POSTURES = frozenset({"xrp_heavy", "slight_xrp_heavy"})


def resolve_join_backoff_bps(*, book_half_spread_bps: Optional[float] = None) -> float:
    """
    Join-side backoff: floor JOIN_BACKOFF_BPS, scale up on wider books.
    Post-M6 soak: 3 bps join captured too little spread (~5 bps avg at 92% pos).
    """
    floor = JOIN_BACKOFF_BPS
    if book_half_spread_bps is None or book_half_spread_bps <= 0:
        return floor
    scaled = round(book_half_spread_bps * JOIN_HALF_SPREAD_FRAC, 2)
    return max(floor, min(PASSIVE_BACKOFF_BPS - 1.0, scaled))


def sell_defense_active(
    *,
    g2_spread_mult: float = 1.0,
    g2_grade: str = "",
    toxic_ratio_30s: float = 0.0,
    mean_markout_30s_pct: float = 0.0,
    recent_fills: int = 0,
) -> tuple[bool, str]:
    """A1: ask-only defense when SELL bleed / adverse flow signals fire."""
    grade = (g2_grade or "").lower()
    if float(g2_spread_mult) > 1.0:
        return True, "g2_brake"
    if grade in ("cautious", "stressed", "defensive"):
        return True, f"g2_{grade}"
    if toxic_ratio_30s >= SELL_DEFENSE_TOXIC_30S:
        return True, f"toxic@{toxic_ratio_30s:.0%}"
    if (
        recent_fills >= SELL_DEFENSE_MIN_FILLS
        and mean_markout_30s_pct < SELL_DEFENSE_MARKOUT_PCT
    ):
        return True, f"markout@{mean_markout_30s_pct:+.3f}%"
    return False, ""


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
    ask_sell_defense: bool = False
    sell_defense_reason: str = ""
    solo_acquisition: bool = False

    @property
    def g7_summary(self) -> str:
        return self.summary


def _inventory_posture(*, inventory_label: str, inventory_skew: float) -> str:
    label = (inventory_label or "").lower()
    if inventory_skew > INVENTORY_SKEW_THRESHOLD:
        return "xrp_heavy"
    if inventory_skew < -INVENTORY_SKEW_THRESHOLD:
        return "rlusd_heavy"
    if "slight_rlusd_heavy" in label:
        return "slight_rlusd_heavy"
    if "slight_xrp_heavy" in label:
        return "slight_xrp_heavy"
    if "rlusd_heavy" in label:
        return "rlusd_heavy"
    if "xrp_heavy" in label:
        return "xrp_heavy"
    return "balanced"


def apply_solo_lane_posture(
    *,
    posture: str,
    peer_lane_empty: bool,
    join_bps: float,
    bid_base: float,
    ask_base: float,
    bid_role: str,
    ask_role: str,
    toxic_ratio_30s: float = 0.0,
    g2_spread_mult: float = 1.0,
) -> tuple[float, float, str, str, bool]:
    """
    Solo empty lane — inventory-aware (v1.5):
    - Accumulating XRP: bid join @ 3bps, ask passive (storefront for sellers only).
    - XRP-heavy: both passive — hold bag, don't sell at touch.
    """
    del join_bps, g2_spread_mult  # join_bps reserved; G2 does not disable solo bid acquire
    if not peer_lane_empty:
        return bid_base, ask_base, bid_role, ask_role, False

    solo_join = SOLO_JOIN_BACKOFF_BPS

    if posture in ACCUMULATE_POSTURES:
        if toxic_ratio_30s >= SOLO_BID_TOXIC_MAX:
            return bid_base, ask_base, bid_role, ask_role, False
        return solo_join, PASSIVE_BACKOFF_BPS, "join", "passive", True

    if posture in HOLD_XRP_POSTURES:
        return PASSIVE_BACKOFF_BPS, PASSIVE_BACKOFF_BPS, "passive", "passive", False

    return bid_base, ask_base, bid_role, ask_role, False


def compute_execution_envelope(
    *,
    inventory_label: str = "",
    inventory_skew: float = 0.0,
    g2_spread_mult: float = 1.0,
    g2_grade: str = "",
    book_half_spread_bps: Optional[float] = None,
    toxic_ratio_30s: float = 0.0,
    mean_markout_30s_pct: float = 0.0,
    recent_fills: int = 0,
    peer_lane_empty: bool = False,
) -> ExecutionEnvelope:
    """
    Rule A: per-side base backoff from inventory.
    Rule B: multiply both sides by max(1, g2.spread_mult) — bid acquire overrides below.
    Rule C: join side uses resolve_join_backoff_bps (book-aware floor).
    Rule D (A1): ask sell-defense — demote ask join + extra ask backoff on bleed signals.
    Rule E (v1.5): solo acquire — bid join + ask passive when accumulating; hold when xrp_heavy.
    """
    join_bps = resolve_join_backoff_bps(book_half_spread_bps=book_half_spread_bps)
    posture = _inventory_posture(inventory_label=inventory_label, inventory_skew=inventory_skew)
    if posture == "xrp_heavy":
        bid_base, ask_base = PASSIVE_BACKOFF_BPS, join_bps
        bid_role, ask_role = "passive", "join"
    elif posture == "rlusd_heavy":
        bid_base, ask_base = join_bps, PASSIVE_BACKOFF_BPS
        bid_role, ask_role = "join", "passive"
    elif posture in ("slight_xrp_heavy", "slight_rlusd_heavy"):
        bid_base = ask_base = PASSIVE_BACKOFF_BPS
        bid_role = ask_role = "wide"
    else:
        bid_base = ask_base = PASSIVE_BACKOFF_BPS
        bid_role = ask_role = "wide"

    bid_base, ask_base, bid_role, ask_role, solo = apply_solo_lane_posture(
        posture=posture,
        peer_lane_empty=peer_lane_empty,
        join_bps=join_bps,
        bid_base=bid_base,
        ask_base=ask_base,
        bid_role=bid_role,
        ask_role=ask_role,
        toxic_ratio_30s=toxic_ratio_30s,
        g2_spread_mult=g2_spread_mult,
    )

    defense, defense_reason = sell_defense_active(
        g2_spread_mult=g2_spread_mult,
        g2_grade=g2_grade,
        toxic_ratio_30s=toxic_ratio_30s,
        mean_markout_30s_pct=mean_markout_30s_pct,
        recent_fills=recent_fills,
    )
    if defense:
        if ask_role == "join":
            ask_base = PASSIVE_BACKOFF_BPS
            ask_role = "passive"
        ask_base = ask_base + ASK_DEFENSE_EXTRA_BPS

    mult = max(1.0, float(g2_spread_mult))
    bid_bps = round(bid_base * mult, 2)
    ask_bps = round(ask_base * mult, 2)

    # v1.5: inventory acquire — bid join ignores G2 widening; ask keeps brake/defense.
    solo_bid_acquire = (
        solo
        and posture in ACCUMULATE_POSTURES
        and toxic_ratio_30s < SOLO_BID_TOXIC_MAX
    )
    if solo_bid_acquire and bid_role == "join":
        bid_bps = SOLO_JOIN_BACKOFF_BPS
        bid_role = "join"
        solo = True
    elif solo and toxic_ratio_30s >= SOLO_ACQUIRE_TOXIC_30S_MAX:
        solo = False

    mult_note = f" × G2 {mult:.2f}" if mult > 1.0 and not solo_bid_acquire else ""
    if mult > 1.0 and solo_bid_acquire:
        mult_note = f" × G2 {mult:.2f} ask-only"
    solo_note = " · solo acquire" if solo else ""
    defense_note = f" · ask defense ({defense_reason})" if defense else ""
    summary = (
        f"G7 {posture}: bid {bid_bps:.1f}bps ({bid_role}) · "
        f"ask {ask_bps:.1f}bps ({ask_role}){mult_note}{solo_note}{defense_note}"
    )
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
        ask_sell_defense=defense,
        sell_defense_reason=defense_reason,
        solo_acquisition=solo,
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
