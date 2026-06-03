"""Unified touch-distance caps for clamps, validation, and refresh heuristics."""

from __future__ import annotations


def effective_max_worse_than_touch_pct(
    *,
    join_touch: bool,
    policy_cap_pct: float = 0.0,
    max_quote_worse_than_touch_pct: float = 0.50,
    competitive_off_touch_max_worse_pct: float = 0.12,
) -> float:
    """
    Max % a quote may sit away from L1 touch (per spread validation / order sync).

    - join_touch L1: use config ceiling (backoff handled separately).
    - off-touch: min(config ceiling, policy visibility cap, or competitive default).
    """
    ceiling = float(max_quote_worse_than_touch_pct)
    off_default = float(competitive_off_touch_max_worse_pct)
    cap = float(policy_cap_pct or 0.0)

    if join_touch:
        return ceiling
    if cap > 0:
        return min(ceiling, cap)
    return min(ceiling, off_default)
