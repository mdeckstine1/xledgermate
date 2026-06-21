"""Layered Quote Decision (v2.3) HUD fields — posture, edge, bleed, permissions."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from strategy.quote_decision_layers.ops_log import peer_lane_token, posture_reason

QD_HUD_VERSION = "2.3.0"

_INTENT_LABELS: Dict[str, str] = {
    "solo_accumulate_on_edge": "ACCUMULATE ON EDGE",
    "patient_solo": "PATIENT (solo)",
    "two_sided_skim": "TWO-SIDED SKIM",
    "inventory_unload": "INVENTORY UNLOAD",
    "hold_off": "HOLD OFF",
    "defensive": "DEFENSIVE",
}

_INTENT_SHORT: Dict[str, str] = {
    "solo_accumulate_on_edge": "ACCUM",
    "patient_solo": "PATIENT",
    "two_sided_skim": "SKIM",
    "inventory_unload": "UNLOAD",
    "hold_off": "HOLD",
    "defensive": "DEF",
}

_BLOCK_CAUSE_LABELS: Dict[str, str] = {
    "edge": "Edge Gate",
    "bleed": "Bleed Protection",
    "inventory": "Inventory CB",
    "tape": "Tape guard",
    "intent": "Intent hold",
    "operator": "Operator override",
}

_DRIFT_LABELS: Dict[str, str] = {
    "neutral": "neutral",
    "mild_xrp": "mild XRP",
    "heavy_xrp": "heavy XRP",
    "mild_rlusd": "mild RLUSD",
    "heavy_rlusd": "heavy RLUSD",
}


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


def _intent_label(intent: str) -> str:
    key = (intent or "").lower()
    if key in _INTENT_LABELS:
        return _INTENT_LABELS[key]
    return key.replace("_", " ").upper() if key else "—"


def _intent_short(intent: str) -> str:
    key = (intent or "").lower()
    if key in _INTENT_SHORT:
        return _INTENT_SHORT[key]
    if not key:
        return "—"
    if "accumulate" in key:
        return "ACCUM"
    if "patient" in key:
        return "PATIENT"
    if "skim" in key:
        return "SKIM"
    return key.replace("_", " ")[:12].upper()


def _drift_label(drift_band: str) -> str:
    return _DRIFT_LABELS.get(drift_band, drift_band.replace("_", " "))


def _block_cause_label(cause: str) -> str:
    key = (cause or "").lower()
    return _BLOCK_CAUSE_LABELS.get(key, cause or "")


def _posture_badge(book_mode: str, posture_reason: str) -> str:
    mode = (book_mode or "").lower()
    if posture_reason == "missing_intel":
        return "CROWDED?"
    if mode == "solo":
        return "SOLO"
    if mode == "sparse":
        return "SPARSE"
    if mode == "crowded":
        return "CROWDED"
    return mode.upper() or "—"


def _side_snapshot(runtime: Mapping[str, Any], side: str) -> Dict[str, Any]:
    prefix = f"qd_{side}_"
    allowed = runtime.get(f"{prefix}allowed")
    pause_cause = str(runtime.get(f"{prefix}pause_cause") or "")
    block_reason = str(runtime.get(f"{prefix}block_reason") or "")
    return {
        "allowed": _bool_or(allowed) if allowed is not None else False,
        "edge_viable": _bool_or(runtime.get(f"{prefix}edge_viable")),
        "implied_bps": _float_or(runtime.get(f"{prefix}implied_bps")),
        "min_edge_bps": _float_or(runtime.get(f"{prefix}min_edge_bps")),
        "bleeding": _bool_or(runtime.get(f"{prefix}bleeding")),
        "block_cause": pause_cause,
        "block_cause_label": _block_cause_label(pause_cause),
        "block_reason": block_reason,
        "size_mult": _float_or(runtime.get(f"{prefix}size_mult")) or 0.0,
    }


def _layer_trace_struct(
    *,
    book_mode: str,
    drift_band: str,
    posture_reason: str,
    peer_lane_token: str,
    peer_count: int,
    intent: str,
    intent_reason: str,
    bid: Mapping[str, Any],
    ask: Mapping[str, Any],
) -> Dict[str, str]:
    drift = _drift_label(drift_band)
    lane = f"{peer_lane_token} ({peer_count})" if peer_count is not None else peer_lane_token
    return {
        "l1": f"{book_mode} · {drift} · peer {lane} · {posture_reason}",
        "l2": f"{intent} — {intent_reason or 'selected'}",
        "l3": (
            f"bid {'PASS' if bid.get('edge_viable') else 'FAIL'} "
            f"{bid.get('implied_bps') or 0:.1f}/{bid.get('min_edge_bps') or 0:.1f} bps · "
            f"ask {'PASS' if ask.get('edge_viable') else 'FAIL'} "
            f"{ask.get('implied_bps') or 0:.1f}/{ask.get('min_edge_bps') or 0:.1f} bps"
        ),
        "l4": (
            f"bid {'ACTIVE' if bid.get('bleeding') else 'clear'} · "
            f"ask {'ACTIVE' if ask.get('bleeding') else 'clear'}"
        ),
        "l5": (
            f"bid {'ALLOWED' if bid.get('allowed') else 'BLOCKED'}"
            f" ×{float(bid.get('size_mult') or 0):.2f} · "
            f"ask {'ALLOWED' if ask.get('allowed') else 'BLOCKED'}"
            f" ×{float(ask.get('size_mult') or 0):.2f}"
            + (f" ({ask.get('block_cause_label') or bid.get('block_cause_label') or ''})" if not bid.get("allowed") or not ask.get("allowed") else "")
        ),
    }


def _derive_health(
    *,
    kill_switch: bool,
    bid: Mapping[str, Any],
    ask: Mapping[str, Any],
    intent: str,
    book_mode: str,
) -> tuple[str, str]:
    if kill_switch:
        return "off", "kill switch active"
    if bid.get("bleeding") or ask.get("bleeding"):
        parts = []
        if bid.get("bleeding"):
            parts.append("bleed bid")
        if ask.get("bleeding"):
            parts.append("bleed ask")
        return "protect", " · ".join(parts)
    bid_ok = bid.get("allowed") and bid.get("edge_viable")
    ask_ok = ask.get("allowed") and ask.get("edge_viable")
    if bid_ok or ask_ok:
        parts = []
        if bid_ok:
            parts.append("edge pass bid")
        if ask_ok:
            parts.append("edge pass ask")
        if not bid.get("bleeding") and not ask.get("bleeding"):
            parts.append("bleed clear")
        return "good", " · ".join(parts)
    intent_l = (intent or "").lower()
    mode = (book_mode or "").lower()
    if mode in ("solo", "sparse") or "patient" in intent_l:
        causes = []
        if not bid.get("edge_viable") and bid.get("block_cause") == "edge":
            causes.append("bid edge fail")
        if not ask.get("edge_viable") and ask.get("block_cause") == "edge":
            causes.append("ask edge fail")
        if not bid.get("allowed") and bid.get("block_cause") == "inventory":
            causes.append("inventory bid")
        if not ask.get("allowed") and ask.get("block_cause") == "inventory":
            causes.append("inventory ask")
        line = " · ".join(causes) if causes else "both sides blocked"
        return "caution", line
    if not bid.get("allowed") and not ask.get("allowed"):
        return "off", "both sides blocked"
    return "caution", "waiting for edge or permission"


def _quoting_line(
    bid: Mapping[str, Any],
    ask: Mapping[str, Any],
    intent: str,
    book_mode: str,
) -> str:
    bid_on = bid.get("allowed")
    ask_on = ask.get("allowed")
    bid_tag = "BID ON" if bid_on else "BID OFF"
    ask_tag = "ASK ON" if ask_on else "ASK OFF"
    parts = [f"{bid_tag} · {ask_tag}"]
    intent_l = (intent or "").lower()
    if "accumulate" in intent_l and (book_mode or "").lower() == "solo":
        if bid_on and bid.get("implied_bps") is not None:
            parts.append(f"solo accumulate, buy edge {bid['implied_bps']:.1f} bps")
        elif not bid_on and not ask_on:
            block = bid.get("block_cause_label") or ask.get("block_cause_label")
            if block:
                parts.append(block)
    elif not bid_on and not ask_on:
        block = bid.get("block_cause_label") or ask.get("block_cause_label")
        if block:
            parts.append(block)
    return " — ".join(parts)


def _primary_block(bid: Mapping[str, Any], ask: Mapping[str, Any]) -> Optional[str]:
    if bid.get("allowed") or ask.get("allowed"):
        return None
    for side in (bid, ask):
        cause = side.get("block_cause_label") or side.get("block_cause")
        if cause:
            return str(cause)
    return "both sides blocked"


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


def build_qd_snapshot(runtime: Mapping[str, Any]) -> Dict[str, Any]:
    """Structured per-cycle QD truth for side cards and trace."""
    rt = dict(runtime)
    peer_empty, peer_count, intel_present = _resolve_peer_lane(rt)

    solo_mode = rt.get("solo_mode")
    if solo_mode is None:
        solo_mode = _bool_or(rt.get("g7_solo_acquisition")) or (peer_empty and intel_present)
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

    posture_r = str(rt.get("posture_reason") or "").strip()
    if not posture_r:
        try:
            cp = float(rt.get("competitor_pressure") or rt.get("book_regime_pressure") or 0)
        except (TypeError, ValueError):
            cp = 0.0
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
    bid = _side_snapshot(rt, "bid")
    ask = _side_snapshot(rt, "ask")
    intent_reason = str(rt.get("qd_intent_reason") or "")

    layer_trace_raw = str(rt.get("qd_layer_trace") or rt.get("qd_layer_summary") or "").strip()
    if not layer_trace_raw and intent:
        bid_p = bid["block_cause"] or bid["block_reason"] or "—"
        ask_p = ask["block_cause"] or ask["block_reason"] or "—"
        layer_trace_raw = (
            f"trace book={book_mode} drift={drift_band} intent={intent} "
            f"bid_e={bid['implied_bps'] or 0:.1f}bps ask_e={ask['implied_bps'] or 0:.1f}bps "
            f"block_bid={bid_p} block_ask={ask_p}"
        )

    return {
        "version": QD_HUD_VERSION,
        "cycle_utc": rt.get("updated_utc"),
        "cycle_id": rt.get("cycle_count"),
        "book_mode": book_mode,
        "solo_mode": solo_mode,
        "peer_lane_token": lane_token,
        "peer_lane_count": peer_count,
        "peer_lane_empty": peer_empty,
        "posture_reason": posture_r,
        "drift_band": drift_band,
        "drift_label": _drift_label(drift_band),
        "intent": intent,
        "intent_label": _intent_label(intent),
        "intent_short": _intent_short(intent),
        "intent_reason": intent_reason,
        "bid": bid,
        "ask": ask,
        "would_quote": _bool_or(rt.get("qd_would_quote")),
        "layer_summary": str(rt.get("qd_layer_summary") or ""),
        "layer_trace_raw": layer_trace_raw,
        "layer_trace_struct": _layer_trace_struct(
            book_mode=book_mode,
            drift_band=drift_band,
            posture_reason=posture_r,
            peer_lane_token=lane_token,
            peer_count=peer_count,
            intent=intent,
            intent_reason=intent_reason,
            bid=bid,
            ask=ask,
        ),
    }


def build_qd_decision_summary(runtime: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Operator-facing derived view for banner and status."""
    rt = dict(runtime)
    bid = snapshot["bid"]
    ask = snapshot["ask"]
    intent = str(snapshot.get("intent") or "")
    book_mode = str(snapshot.get("book_mode") or "")
    posture_r = str(snapshot.get("posture_reason") or "")

    kill = _bool_or(rt.get("kill_switch_active"))
    health, health_line = _derive_health(
        kill_switch=kill,
        bid=bid,
        ask=ask,
        intent=intent,
        book_mode=book_mode,
    )

    badge = _posture_badge(book_mode, posture_r)
    peer_count = snapshot.get("peer_lane_count", 0)
    posture_detail = f"{posture_r.replace('_', ' ')} · peers {peer_count}"

    quoting_line = _quoting_line(bid, ask, intent, book_mode)
    bid_on = bid.get("allowed")
    ask_on = ask.get("allowed")
    quoting_short = f"{'B ON' if bid_on else 'B OFF'} / {'A ON' if ask_on else 'A OFF'}"

    intent_line = f"{snapshot.get('intent_label', '—')} · drift {snapshot.get('drift_label', '—')}"

    return {
        "health": health,
        "health_line": health_line,
        "posture_badge": badge,
        "posture_detail": posture_detail,
        "intent_line": intent_line,
        "quoting_line": quoting_line,
        "quoting_short": quoting_short,
        "bid_allowed": bid_on,
        "ask_allowed": ask_on,
        "primary_block": _primary_block(bid, ask),
        "protection_active": bid.get("bleeding") or ask.get("bleeding"),
        "solo_accumulate": "accumulate" in intent.lower() and book_mode == "solo",
        "engine_running": not kill,
        "quoting_active": bid_on or ask_on,
    }


def build_qd_hud_fields(runtime: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Enrich runtime snapshot for layered QD HUD panels.

    Fills gaps when ws-engine has not yet restarted after deploy (HUD synthesis).
    """
    rt = dict(runtime)
    snapshot = build_qd_snapshot(rt)
    summary = build_qd_decision_summary(rt, snapshot)

    bid = snapshot["bid"]
    ask = snapshot["ask"]
    posture_class = _qd_posture_class(
        book_mode=snapshot["book_mode"],
        solo_mode=snapshot["solo_mode"],
        intent=snapshot["intent"],
        bid_edge_viable=bid["edge_viable"],
        ask_edge_viable=ask["edge_viable"],
        bid_bleeding=bid["bleeding"],
        ask_bleeding=ask["bleeding"],
    )

    return {
        "qd_hud_version": QD_HUD_VERSION,
        "qd_snapshot": snapshot,
        "qd_decision_summary": summary,
        "peer_lane_count": snapshot["peer_lane_count"],
        "peer_lane_empty": snapshot["peer_lane_empty"],
        "solo_mode": snapshot["solo_mode"],
        "posture_reason": snapshot["posture_reason"],
        "qd_peer_lane_token": snapshot["peer_lane_token"],
        "qd_book_mode": snapshot["book_mode"],
        "qd_drift_band": snapshot["drift_band"],
        "qd_intent_reason": snapshot["intent_reason"],
        "qd_bid_edge_viable": bid["edge_viable"],
        "qd_ask_edge_viable": ask["edge_viable"],
        "qd_bid_min_edge_bps": bid["min_edge_bps"],
        "qd_ask_min_edge_bps": ask["min_edge_bps"],
        "qd_bid_pause_cause": bid["block_cause"],
        "qd_ask_pause_cause": ask["block_cause"],
        "qd_bid_bleeding": bid["bleeding"],
        "qd_ask_bleeding": ask["bleeding"],
        "qd_layer_trace": snapshot["layer_trace_raw"],
        "qd_posture_class": posture_class,
        "qd_bid_allowed": bid["allowed"],
        "qd_ask_allowed": ask["allowed"],
        "qd_permissions_summary": (
            f"bid={'ON' if bid['allowed'] else 'OFF'} · ask={'ON' if ask['allowed'] else 'OFF'}"
            f" · bid×{bid['size_mult']:.2f} · ask×{ask['size_mult']:.2f}"
        ),
    }


__all__ = [
    "QD_HUD_VERSION",
    "build_qd_decision_summary",
    "build_qd_hud_fields",
    "build_qd_snapshot",
]
