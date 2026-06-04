"""Shared toxicity thresholds — one source for fill quality and quoting gates."""

from __future__ import annotations

from core.perception import Profile
from strategy.fill_quality import FillQualityState


def effective_toxic_ratio(
    fq: FillQualityState,
    *,
    min_fills_for_gates: int = 8,
) -> float:
    """
    Rolling adverse ratio used for off-book / pause-side / refresh-pause gates.

    Below min_fills_for_gates returns 0 so small samples (e.g. 2/4 = 50%) do not
    empty the storefront. Fill-quality sizing may still react earlier (see assess).
    """
    need = max(3, int(min_fills_for_gates))
    if fq.recent_fills < need:
        return 0.0
    return max(fq.toxic_ratio, fq.toxic_ratio_30s)


def gates_apply_for_fill_count(
    recent_fills: int,
    *,
    min_fills_for_gates: int = 8,
) -> bool:
    """Whether toxicity-driven quoting gates may engage."""
    return recent_fills >= max(3, int(min_fills_for_gates))
