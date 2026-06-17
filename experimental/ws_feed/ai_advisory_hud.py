"""F2 soak-safe HUD advisory stub — rate-limited AIAdvisorySignal display only."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from experimental.ai_analysis.base import AIAdvisorySignal

HUD_ADVISORY_MIN_INTERVAL_S = 300.0

_last_emit_monotonic: float = 0.0
_cached_fields: Dict[str, Any] = {}


def _pressure(runtime: Dict[str, Any]) -> float:
    peer_count = int(runtime.get("peer_lane_count") or 0)
    if peer_count > 0:
        try:
            return float(runtime.get("peer_pressure") or runtime.get("peer_pressure_score") or 0.5)
        except (TypeError, ValueError):
            return 0.5
    try:
        return float(
            runtime.get("book_regime_pressure")
            or runtime.get("competitor_pressure")
            or 0.5
        )
    except (TypeError, ValueError):
        return 0.5


def derive_advisory_signal(runtime: Dict[str, Any]) -> AIAdvisorySignal:
    """Map scrape pressure + book skew to advisory mults (never touches reservation)."""
    pressure = _pressure(runtime)
    skew_label = str(runtime.get("book_side_skew_label") or "")
    skim_harder = pressure < 0.25
    vol_mult = 0.92 if skim_harder else (1.0 if pressure < 0.55 else 1.05)
    size_mult = 1.10 if skim_harder else (1.0 if pressure < 0.55 else 0.92)
    if skew_label == "bid_heavy" and runtime.get("inventory_label") == "rlusd_heavy":
        size_mult = min(size_mult, 1.05)
    confidence = max(0.25, min(0.95, 1.0 - pressure))
    rationale = (
        f"pressure={pressure:.2f} ({'peer' if int(runtime.get('peer_lane_count') or 0) > 0 else 'regime'}); "
        f"skew={skew_label or 'unknown'}; "
        + ("low pressure → skim harder advisory" if skim_harder else "neutral/defensive advisory")
    )
    return AIAdvisorySignal(
        vol_mult=round(vol_mult, 3),
        size_mult=round(size_mult, 3),
        confidence=round(confidence, 3),
        skim_harder=skim_harder,
        rationale=rationale,
        source="hud_pressure_stub",
    )


def advisory_hud_fields(
    runtime: Dict[str, Any],
    *,
    min_interval_s: float = HUD_ADVISORY_MIN_INTERVAL_S,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Rate-limited F2 HUD fields — refreshes signal at most every `min_interval_s`.

    Still maps existing Intelligence tab fields (`ai_edge_quality`, `ai_is_skimmable`).
    """
    global _last_emit_monotonic, _cached_fields
    t = now if now is not None else time.monotonic()
    if _cached_fields and (t - _last_emit_monotonic) < min_interval_s:
        return dict(_cached_fields)

    sig = derive_advisory_signal(runtime)
    _cached_fields = {
        "ai_advisory_vol_mult": sig.vol_mult,
        "ai_advisory_size_mult": sig.size_mult,
        "ai_advisory_skim_harder": sig.skim_harder,
        "ai_advisory_confidence": sig.confidence,
        "ai_advisory_rationale": sig.rationale,
        "ai_advisory_source": sig.source,
        "ai_edge_quality": sig.confidence,
        "ai_is_skimmable": sig.skim_harder and sig.confidence >= 0.5,
        "ai_rationale": sig.rationale,
    }
    _last_emit_monotonic = t
    return dict(_cached_fields)


def reset_advisory_cache() -> None:
    """Test helper."""
    global _last_emit_monotonic, _cached_fields
    _last_emit_monotonic = 0.0
    _cached_fields = {}
