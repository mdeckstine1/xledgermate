"""
Layer 1 — Posture detection (read-only).

Single source of truth for book mode, inventory drift band, and per-side fill
quality. Downstream layers must not re-derive these from raw inputs.
"""

from __future__ import annotations

from strategy.fill_quality import FillQualityState
from strategy.quote_decision_layers.types import (
    BookMode,
    BookPosture,
    DriftBand,
    InventoryDrift,
    Posture,
    SideFillQuality,
)

# Wide tolerance — grow from profitable edges, not forced rebalancing.
DRIFT_MILD = 0.08
DRIFT_HEAVY = 0.16

BLEED_MIN_FILLS = 3
BLEED_TOXIC_RATIO = 0.35
BLEED_MARKOUT_PCT = -0.04


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
    *,
    fill_count: int,
    toxic_ratio_30s: float,
    mean_markout_30s_pct: float,
) -> SideFillQuality:
    bleeding = False
    reason = ""
    if fill_count >= BLEED_MIN_FILLS:
        if toxic_ratio_30s >= BLEED_TOXIC_RATIO:
            bleeding = True
            reason = f"toxic_30s={toxic_ratio_30s:.0%}>={BLEED_TOXIC_RATIO:.0%}"
        elif mean_markout_30s_pct <= BLEED_MARKOUT_PCT:
            bleeding = True
            reason = f"markout_30s={mean_markout_30s_pct:+.3f}%<={BLEED_MARKOUT_PCT:+.3f}%"

    return SideFillQuality(
        fill_count=fill_count,
        toxic_ratio_30s=toxic_ratio_30s,
        mean_markout_30s_pct=mean_markout_30s_pct,
        bleeding=bleeding,
        bleed_reason=reason,
    )


def _resolve_solo_book(
    *,
    peer_lane_empty: bool,
    peer_lane_count: int,
    low_book_pressure: bool,
) -> bool:
    """
    Solo lane when peers are absent or book pressure is low.

    peer_lane_count==0 with low pressure does NOT infer solo — legacy paths
    default to crowded unless peer_lane_empty is explicit or count==1 (sparse).
    """
    if peer_lane_empty:
        return True
    if low_book_pressure and peer_lane_count == 1:
        return True
    return False


def build_posture(
    *,
    xrp_ratio: float,
    inventory_label: str,
    fill_quality: FillQualityState,
    target_xrp_ratio: float,
    market_condition: str,
    mid_momentum_pct: float,
    peer_lane_empty: bool = False,
    peer_lane_count: int = 0,
    low_book_pressure: bool = False,
) -> Posture:
    """Construct Layer 1 posture from engine cycle inputs."""
    deviation = xrp_ratio - target_xrp_ratio
    solo = _resolve_solo_book(
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        low_book_pressure=low_book_pressure,
    )
    lane_count = peer_lane_count if peer_lane_count > 0 else (0 if solo else 3)

    fq = fill_quality
    buy_q = _side_quality(
        fill_count=fq.buy_fill_count,
        toxic_ratio_30s=fq.buy_toxic_ratio_30s,
        mean_markout_30s_pct=fq.buy_mean_markout_30s_pct,
    )
    sell_q = _side_quality(
        fill_count=fq.sell_fill_count,
        toxic_ratio_30s=fq.sell_toxic_ratio_30s,
        mean_markout_30s_pct=fq.sell_mean_markout_30s_pct,
    )

    return Posture(
        book=BookPosture(
            solo=solo,
            peer_lane_count=max(0, int(lane_count)),
            mode=_book_mode(solo=solo, peer_lane_count=lane_count),
        ),
        inventory=InventoryDrift(
            xrp_ratio=xrp_ratio,
            target_xrp_ratio=target_xrp_ratio,
            deviation=deviation,
            label=inventory_label,
            band=_drift_band(deviation),
        ),
        buy_quality=buy_q,
        sell_quality=sell_q,
        market_condition=(market_condition or "neutral").strip().lower(),
        mid_momentum_pct=float(mid_momentum_pct),
    )
