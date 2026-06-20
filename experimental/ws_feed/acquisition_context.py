"""Acquisition posture helpers — solo lane opportunities and fill context."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from experimental.ws_feed.peer_lane_quoting import is_peer_lane_empty

SOLO_ACQUIRE_TOXIC_30S_MAX = 0.20
ACQUISITION_POSTURES = frozenset({"balanced", "rlusd_heavy", "slight_rlusd_heavy"})


def _norm_posture(label: str) -> str:
    return (label or "").strip().lower()


def solo_acquire_opportunity(
    *,
    peer_lane_empty: bool,
    toxic_ratio_30s: float,
    g2_spread_mult: float,
    would_quote: bool = True,
) -> bool:
    """Cycles where A2 solo lane logic could apply (empty band, low toxic, no G2 spread brake)."""
    if not would_quote or not peer_lane_empty:
        return False
    if float(g2_spread_mult) > 1.0:
        return False
    return float(toxic_ratio_30s) < SOLO_ACQUIRE_TOXIC_30S_MAX


def solo_acquire_bid_join_opportunity(
    *,
    peer_lane_empty: bool,
    toxic_ratio_30s: float,
    g2_spread_mult: float,
    inventory_label: str,
    would_quote: bool = True,
) -> bool:
    """Strict acquisition window: balanced / rlusd_heavy with bid-join intent."""
    if not solo_acquire_opportunity(
        peer_lane_empty=peer_lane_empty,
        toxic_ratio_30s=toxic_ratio_30s,
        g2_spread_mult=g2_spread_mult,
        would_quote=would_quote,
    ):
        return False
    return _norm_posture(inventory_label) in ACQUISITION_POSTURES


def solo_acquire_fired(*, g7_solo_acquisition: bool) -> bool:
    return bool(g7_solo_acquisition)


def solo_acquire_bid_join_fired(*, g7_solo_acquisition: bool, g7_bid_role: str) -> bool:
    """Solo edge acquire: passive bid (v1.6) or legacy join."""
    role = (g7_bid_role or "").strip().lower()
    return bool(g7_solo_acquisition) and role in ("join", "passive")


def extract_acquisition_fill_context(
    engine_dec: Optional[Mapping[str, Any]],
    *,
    competitor_intel: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Snapshot at fill time for M6 JSONL + CSV notes."""
    ed = engine_dec or {}
    intel = competitor_intel or {}
    peer_empty = is_peer_lane_empty(intel) if intel else bool(ed.get("peer_lane_empty"))
    return {
        "inventory_label": str(ed.get("inventory_label") or ""),
        "g7_solo_acquisition": bool(ed.get("g7_solo_acquisition")),
        "g7_bid_role": str(ed.get("g7_bid_role") or ""),
        "g7_ask_role": str(ed.get("g7_ask_role") or ""),
        "g7_ask_sell_defense": bool(ed.get("g7_ask_sell_defense")),
        "g4_grade": str(ed.get("g4_grade") or ""),
        "g2_grade": str(ed.get("g2_grade") or ""),
        "g2_spread_mult": float(ed.get("g2_spread_mult") or 1.0),
        "peer_lane_empty": peer_empty,
        "worst_vs_touch_bps": float(ed.get("worst_vs_touch_bps") or 0.0),
    }
