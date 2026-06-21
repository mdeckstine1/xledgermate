"""Layered Quote Decision (v2.3) HUD fields — posture, edge, bleed, permissions."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from strategy.quote_decision_layers.ops_log import peer_lane_token, posture_reason

QD_HUD_VERSION = "2.3.0"


def _bool_or(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    return bool(val)


def _int_or(val: Any, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _float_or(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _peer_intel_present(runtime: Mapping[str, Any]) -> bool:
    ci = runtime.get("competitor_intel")
    if isinstance(ci, dict) and (
        "peer_lane_count" in ci or "peer_lane_empty" in ci or ci.get("peer_lane_count") is not None
    ):
        return True
    return (
        runtime.get("peer_lane_count") is not None
        or runtime.get("g4_peer_lane_count") is not None
        or runtime.get("peer_lane_empty") is not None
    )


def _resolve_peer_lane(runtime: Mapping[str, Any]) -> tuple[bool, int, bool]:
    """Return (peer_lane_empty, peer_lane_count, intel_present)."""
    ci = runtime.get("competitor_intel") if isinstance(runtime.get("competitor_intel"), dict) else {}
    intel_present = _peer_intel_present(runtime)
    count_raw = (
        runtime.get("peer_lane_count")
        if runtime.get("peer_lane_count") is not None
        else runtime.get("g4_peer_lane_count")
        if runtime.get("g4_peer_lane_count") is not None
        else ci.get("peer_lane_count")
    )
    count = _int_or(count_raw, 0)
    empty = _bool_or(runtime.get("peer_lane_empty") or ci.get("peer_lane_empty"))
    if intel_present and count <= 0:
        empty = True
    return empty, count, intel_present


def _qd_posture_class(
    *,
    book_mode: str,
    solo_mode: bool,
    intent: str,
    bid_edge_viable: bool,
    ask_edge_viable: bool,
    bid_bleeding: bool,
    ask_bleeding: bool,
) -> str:
    """HUD color token: good | warn | info | bad | neutral."""
    if bid_bleeding or ask_bleeding:
        return "bad"
    mode = (book_mode or "").lower()
    intent_l = (intent or "").lower()
    if solo_mode and mode == "solo":
        if "accumulate" in intent_l and (bid_edge_viable or ask_edge_viable):
            return "good"
        if "patient" in intent_l or (not bid_edge_viable and not ask_edge_viable):
            return "warn"
        return "good"
    if mode in ("sparse", "crowded"):
        return "info"
    return "neutral"


def build_qd_hud_fields(runtime: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Enrich runtime snapshot for layered QD HUD panels.

    Fills gaps when ws-engine has not yet restarted after deploy (HUD synthesis).
    """
    rt = dict(runtime)
    peer_empty, peer_count, intel_present = _resolve_peer_lane(rt)

    solo_mode = rt.get("solo_mode")
    if solo_mode is None:
        solo_mode = _bool_or(rt.get("g7_solo_acquisition")) or (
            peer_empty and intel_present
        )
    solo_mode = _bool_or(solo_mode)

    book_mode = str(rt.get("qd_book_mode") or "").strip()
    if not book_mode:
        if not intel_present:
            book_mode = "crowded"
        elif solo_mode:
            book_mode = "solo"
        elif peer_count <= 1:
            book_mode = "sparse"
        else:
            book_mode = "crowded"

    drift_band = str(rt.get("qd_drift_band") or rt.get("inventory_label") or "neutral")
    if drift_band in ("balanced", "xrp_heavy", "rlusd_heavy", "slight_xrp_heavy", "slight_rlusd_heavy"):
        label = drift_band.lower()
        if "heavy_xrp" in label or label == "xrp_heavy":
            drift_band = "heavy_xrp"
        elif "heavy" in label and "rlusd" in label:
            drift_band = "heavy_rlusd"
        elif "xrp" in label:
            drift_band = "mild_xrp"
        elif "rlusd" in label:
            drift_band = "mild_rlusd"
        else:
            drift_band = "neutral"

    try:
        cp = float(rt.get("competitor_pressure") or rt.get("book_regime_pressure") or 0)
    except (TypeError, ValueError):
        cp = 0.0

    posture_r = str(rt.get("posture_reason") or "").strip()
    if not posture_r:
        posture_r = posture_reason(
            solo=solo_mode,
            peer_lane_empty=peer_empty,
            peer_lane_count=peer_count,
            intel_present=intel_present,
            low_book_pressure=cp < 0.35,
        )

    lane_token = str(rt.get("qd_peer_lane_token") or "").strip()
    if not lane_token:
        lane_token = peer_lane_token(
            peer_lane_empty=peer_empty,
            peer_lane_count=peer_count,
            intel_present=intel_present,
        )

    intent = str(rt.get("qd_intent") or "")
    bid_edge_v = _bool_or(rt.get("qd_bid_edge_viable"))
    ask_edge_v = _bool_or(rt.get("qd_ask_edge_viable"))
    bid_bleed = _bool_or(rt.get("qd_bid_bleeding"))
    ask_bleed = _bool_or(rt.get("qd_ask_bleeding"))

    layer_trace = str(rt.get("qd_layer_trace") or rt.get("qd_layer_summary") or "").strip()
    if not layer_trace and intent:
        bid_bps = _float_or(rt.get("qd_bid_implied_bps"))
        ask_bps = _float_or(rt.get("qd_ask_implied_bps"))
        bid_p = rt.get("qd_bid_pause_cause") or rt.get("qd_bid_block_reason") or "—"
        ask_p = rt.get("qd_ask_pause_cause") or rt.get("qd_ask_block_reason") or "—"
        layer_trace = (
            f"trace book={book_mode} drift={drift_band} intent={intent} "
            f"bid_e={bid_bps or 0:.1f}bps ask_e={ask_bps or 0:.1f}bps "
            f"pause_bid={bid_p} pause_ask={ask_p}"
        )

    posture_class = _qd_posture_class(
        book_mode=book_mode,
        solo_mode=solo_mode,
        intent=intent,
        bid_edge_viable=bid_edge_v,
        ask_edge_viable=ask_edge_v,
        bid_bleeding=bid_bleed,
        ask_bleeding=ask_bleed,
    )

    bid_allowed = rt.get("qd_bid_allowed")
    ask_allowed = rt.get("qd_ask_allowed")

    return {
        "qd_hud_version": QD_HUD_VERSION,
        "peer_lane_count": peer_count,
        "peer_lane_empty": peer_empty,
        "solo_mode": solo_mode,
        "posture_reason": posture_r,
        "qd_peer_lane_token": lane_token,
        "qd_book_mode": book_mode,
        "qd_drift_band": drift_band,
        "qd_intent_reason": str(rt.get("qd_intent_reason") or ""),
        "qd_bid_edge_viable": bid_edge_v,
        "qd_ask_edge_viable": ask_edge_v,
        "qd_bid_min_edge_bps": _float_or(rt.get("qd_bid_min_edge_bps")),
        "qd_ask_min_edge_bps": _float_or(rt.get("qd_ask_min_edge_bps")),
        "qd_bid_pause_cause": str(rt.get("qd_bid_pause_cause") or ""),
        "qd_ask_pause_cause": str(rt.get("qd_ask_pause_cause") or ""),
        "qd_bid_bleeding": bid_bleed,
        "qd_ask_bleeding": ask_bleed,
        "qd_layer_trace": layer_trace,
        "qd_posture_class": posture_class,
        "qd_bid_allowed": bid_allowed,
        "qd_ask_allowed": ask_allowed,
        "qd_permissions_summary": (
            f"bid={'ON' if bid_allowed else 'OFF'} · ask={'ON' if ask_allowed else 'OFF'}"
            f" · bid×{float(rt.get('qd_bid_size_mult') or 0):.2f}"
            f" · ask×{float(rt.get('qd_ask_size_mult') or 0):.2f}"
        ),
    }


__all__ = ["QD_HUD_VERSION", "build_qd_hud_fields"]
