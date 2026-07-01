"""
Layer 1 — Posture detection (read-only).

Single source of truth for book mode, inventory drift band, and per-side fill
quality. Downstream layers must not re-derive these from raw inputs.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from experimental.ws_feed.quote_decision.types import (
    BookMode,
    BookPosture,
    CycleQuoteInputs,
    DriftBand,
    InventoryDrift,
    PostureSnapshot,
    SideFillQuality,
)

# Wide tolerance — growth from edge, not forced rebalancing (principle 3).
DRIFT_MILD = 0.08
DRIFT_HEAVY = 0.16

BLEED_RECENT_FILLS_MIN = 3
BLEED_CAPTURE_XRP = 0.0
BLEED_AVG_BPS = 0.0


def _drift_band(deviation: float) -> DriftBand:
    if deviation >= DRIFT_HEAVY:
        return DriftBand.HEAVY_XRP
    if deviation >= DRIFT_MILD:
        return DriftBand.MILD_XRP
    if deviation <= -DRIFT_HEAVY:
        return DriftBand.HEAVY_RLUSD
    if deviation <= -DRIFT_MILD:
        return DriftBand.MILD_RLUSD
    return DriftBand.NEUTRAL


def _book_mode(*, solo: bool, peer_lane_count: int) -> BookMode:
    if solo:
        return BookMode.SOLO
    if peer_lane_count <= 2:
        return BookMode.SPARSE
    return BookMode.CROWDED


def _side_quality(
    fills: Sequence[Mapping[str, Any]],
    *,
    session_capture: Optional[float],
) -> SideFillQuality:
    caps: list[float] = []
    bps_list: list[float] = []
    for row in fills:
        try:
            cap = float(row.get("capture_xrp") or row.get("cap") or 0.0)
            xrp = float(row.get("xrp_amount") or row.get("xrp") or 0.0)
        except (TypeError, ValueError):
            continue
        caps.append(cap)
        if xrp > 0 and cap != 0:
            bps_list.append(cap / xrp * 10_000.0)

    recent_cap = sum(caps)
    avg_bps = sum(bps_list) / len(bps_list) if bps_list else None
    n = len(fills)

    bleeding = False
    reason = ""
    if n >= BLEED_RECENT_FILLS_MIN:
        if recent_cap < BLEED_CAPTURE_XRP:
            bleeding = True
            reason = f"recent_cap={recent_cap:.4f}<{BLEED_CAPTURE_XRP}"
        elif avg_bps is not None and avg_bps < BLEED_AVG_BPS:
            bleeding = True
            reason = f"recent_avg_bps={avg_bps:.1f}<{BLEED_AVG_BPS}"

    return SideFillQuality(
        fill_count=n,
        session_capture_xrp=float(session_capture or 0.0),
        recent_capture_xrp=recent_cap,
        avg_edge_bps=round(avg_bps, 2) if avg_bps is not None else None,
        bleeding=bleeding,
        bleed_reason=reason,
    )


def build_posture_snapshot(inputs: CycleQuoteInputs) -> PostureSnapshot:
    """Construct Layer 1 snapshot from cycle inputs."""
    deviation = inputs.xrp_ratio - inputs.target_xrp_ratio
    solo = bool(
        inputs.peer_lane_empty
        or (inputs.peer_lane_known and inputs.peer_lane_count <= 0)
    )

    return PostureSnapshot(
        book=BookPosture(
            solo=solo,
            peer_lane_count=max(0, int(inputs.peer_lane_count)),
            mode=_book_mode(solo=solo, peer_lane_count=inputs.peer_lane_count),
        ),
        inventory=InventoryDrift(
            xrp_ratio=inputs.xrp_ratio,
            target_xrp_ratio=inputs.target_xrp_ratio,
            deviation=deviation,
            label=(inputs.inventory_label or "balanced").strip().lower(),
            band=_drift_band(deviation),
        ),
        buy_quality=_side_quality(
            inputs.recent_buys,
            session_capture=inputs.session_buy_capture_xrp,
        ),
        sell_quality=_side_quality(
            inputs.recent_sells,
            session_capture=inputs.session_sell_capture_xrp,
        ),
        toxic_ratio_30s=float(inputs.toxic_ratio_30s or 0.0),
        g2_spread_mult=float(inputs.g2_spread_mult or 1.0),
        g2_grade=(inputs.g2_grade or "").strip().lower(),
    )


__all__ = [
    "DRIFT_HEAVY",
    "DRIFT_MILD",
    "build_posture_snapshot",
]
