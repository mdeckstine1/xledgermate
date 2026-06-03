"""Shared toxicity thresholds — one source for fill quality and quoting gates."""

from __future__ import annotations

from core.perception import Profile
from strategy.fill_quality import FillQualityState


def effective_toxic_ratio(fq: FillQualityState) -> float:
    """Rolling adverse ratio; needs ≥3 fills before gates engage."""
    if fq.recent_fills < 3:
        return 0.0
    return max(fq.toxic_ratio, fq.toxic_ratio_30s)
