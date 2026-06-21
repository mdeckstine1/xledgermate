"""
Layer 1 — Posture detection (read-only).

Single source of truth for book mode, inventory drift band, and per-side fill
quality. Downstream layers must not re-derive these from raw inputs.

Peer-lane inputs are normalized in ``_normalize_peer_lane`` before solo/mode
resolution. Layer 5 alone sets final bid/ask permissions (see ``decision.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.market_conditions import (
    CONDITION_DEFENSIVE,
    CONDITION_FAVORABLE,
    CONDITION_HOSTILE,
    CONDITION_NEUTRAL,
)
from strategy.fill_quality import FillQualityState
from strategy.quote_decision_layers.types import (
    BookMode,
    BookPosture,
    DriftBand,
    InventoryDrift,
    Posture,
    SideFillQuality,
)

# Inventory drift bands — wide tolerance; grow from edge, not forced rebalance.
DRIFT_MILD = 0.08
DRIFT_HEAVY = 0.16

# Bleed detection (Layer 1 read-only signals; Layer 4 / L5 apply pauses).
BLEED_MIN_FILLS = 3
BLEED_TOXIC_RATIO = 0.35
BLEED_MARKOUT_PCT = -0.04

# When peer count is unknown (0) and book is not solo, assume crowded lane depth
# so sparse/crowded classification matches legacy conservative behavior.
PEER_LANE_COUNT_CROWDED_ASSUMED = 3

# Solo via low book pressure requires exactly one reported peer (sparse lane).
SOLO_SPARSE_PEER_COUNT = 1

_KNOWN_MARKET_CONDITIONS = frozenset(
    {
        CONDITION_FAVORABLE,
        CONDITION_NEUTRAL,
        CONDITION_DEFENSIVE,
        CONDITION_HOSTILE,
    }
)


@dataclass(frozen=True)
class _NormalizedPeerLane:
    """Validated peer-lane inputs for posture (empty flag wins over count)."""

    peer_lane_empty: bool
    peer_lane_count: int
    count_for_mode: int


def _finite_float(value: float, *, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return v


def _clamp_unit_ratio(value: float, *, default: float = 0.5) -> float:
    """Clamp portfolio XRP ratio inputs to [0, 1]."""
    v = _finite_float(value, default=default)
    return max(0.0, min(1.0, v))


def _clamp_non_negative_int(value: int | float, *, default: int = 0) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, v)


def _clamp_toxic_ratio(value: float) -> float:
    return max(0.0, min(1.0, _finite_float(value, default=0.0)))


def _normalize_market_condition(market_condition: str) -> str:
    """Lowercase known condition tokens; unknown → neutral (no quoting change)."""
    raw = (market_condition or CONDITION_NEUTRAL).strip().lower()
    if raw in _KNOWN_MARKET_CONDITIONS:
        return raw
    return CONDITION_NEUTRAL


def _normalize_inventory_label(inventory_label: str, deviation: float) -> str:
    """
    Normalize inventory label for posture display.

    When callers omit a label, derive a coarse tag from deviation so L1 stays
    self-consistent with the drift band.
    """
    label = (inventory_label or "").strip().lower()
    if label:
        return label
    if deviation >= DRIFT_MILD:
        return "xrp_heavy"
    if deviation <= -DRIFT_MILD:
        return "rlusd_heavy"
    return "balanced"


def _normalize_peer_lane(
    *,
    peer_lane_empty: bool,
    peer_lane_count: int,
) -> _NormalizedPeerLane:
    """
    Reconcile ``peer_lane_empty`` and ``peer_lane_count``.

    Rules (preserve legacy quoting behavior):
      - ``peer_lane_empty=True`` always wins; count is forced to 0.
      - Otherwise count is non-negative int.
      - Unknown count (0) on non-empty lane uses ``PEER_LANE_COUNT_CROWDED_ASSUMED``
        for sparse vs crowded mode only — does not imply solo.
    """
    empty = bool(peer_lane_empty)
    count = _clamp_non_negative_int(peer_lane_count)

    if empty and count > 0:
        # Contradictory upstream scrape — treat as confirmed empty (solo path).
        count = 0

    if empty:
        return _NormalizedPeerLane(
            peer_lane_empty=True,
            peer_lane_count=0,
            count_for_mode=0,
        )

    count_for_mode = count if count > 0 else PEER_LANE_COUNT_CROWDED_ASSUMED
    return _NormalizedPeerLane(
        peer_lane_empty=False,
        peer_lane_count=count,
        count_for_mode=count_for_mode,
    )


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
    fills = _clamp_non_negative_int(fill_count)
    toxic = _clamp_toxic_ratio(toxic_ratio_30s)
    markout = _finite_float(mean_markout_30s_pct, default=0.0)

    bleeding = False
    reason = ""
    if fills >= BLEED_MIN_FILLS:
        if toxic >= BLEED_TOXIC_RATIO:
            bleeding = True
            reason = f"toxic_30s={toxic:.0%}>={BLEED_TOXIC_RATIO:.0%}"
        elif markout <= BLEED_MARKOUT_PCT:
            bleeding = True
            reason = f"markout_30s={markout:+.3f}%<={BLEED_MARKOUT_PCT:+.3f}%"

    return SideFillQuality(
        fill_count=fills,
        toxic_ratio_30s=toxic,
        mean_markout_30s_pct=markout,
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
    Determine solo book status (Layer 1 only — not final quote permission).

    Solo when:
      1. ``peer_lane_empty`` is True (confirmed or normalized empty lane), or
      2. ``low_book_pressure`` and exactly ``SOLO_SPARSE_PEER_COUNT`` peer(s).

    ``peer_lane_count==0`` without ``peer_lane_empty`` does NOT infer solo —
    legacy paths default to crowded unless the empty flag or sparse rule applies.
    """
    if peer_lane_empty:
        return True
    if low_book_pressure and peer_lane_count == SOLO_SPARSE_PEER_COUNT:
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
    ratio = _clamp_unit_ratio(xrp_ratio)
    target = _clamp_unit_ratio(target_xrp_ratio, default=0.55)
    deviation = ratio - target

    peer = _normalize_peer_lane(
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
    )
    solo = _resolve_solo_book(
        peer_lane_empty=peer.peer_lane_empty,
        peer_lane_count=peer.peer_lane_count,
        low_book_pressure=bool(low_book_pressure),
    )

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

    label = _normalize_inventory_label(inventory_label, deviation)

    return Posture(
        book=BookPosture(
            solo=solo,
            peer_lane_count=peer.peer_lane_count,
            mode=_book_mode(solo=solo, peer_lane_count=peer.count_for_mode),
        ),
        inventory=InventoryDrift(
            xrp_ratio=ratio,
            target_xrp_ratio=target,
            deviation=deviation,
            label=label,
            band=_drift_band(deviation),
        ),
        buy_quality=buy_q,
        sell_quality=sell_q,
        market_condition=_normalize_market_condition(market_condition),
        mid_momentum_pct=_finite_float(mid_momentum_pct, default=0.0),
    )
