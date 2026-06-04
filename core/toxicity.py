"""Shared toxicity thresholds — one source for fill quality and quoting gates."""

from __future__ import annotations

from core.perception import Profile
from strategy.fill_quality import FillQualityState


def _exit_no_touch_ratio(profile: Profile) -> float:
    enter = float(profile.toxic_no_touch_ratio)
    return float(getattr(profile, "toxic_no_touch_exit_ratio", enter * 0.75))


def update_toxic_off_touch_latch(
    latched: bool,
    fq: FillQualityState,
    profile: Profile,
) -> bool:
    """
    Hysteresis for off-book: enter at toxic_no_touch_ratio, exit below exit ratio.
    """
    min_fills = int(getattr(profile, "toxic_min_fills_for_gates", 8))
    if not gates_apply_for_fill_count(fq.recent_fills, min_fills_for_gates=min_fills):
        return False
    toxic = effective_toxic_ratio(fq, min_fills_for_gates=min_fills)
    enter = float(profile.toxic_no_touch_ratio)
    exit_ratio = _exit_no_touch_ratio(profile)
    if toxic >= enter:
        return True
    if toxic < exit_ratio:
        return False
    return latched


def toxic_off_touch_active(
    latched: bool,
    fq: FillQualityState,
    profile: Profile,
) -> bool:
    """Whether dynamic policy should force off-book from toxicity."""
    return update_toxic_off_touch_latch(latched, fq, profile)


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
