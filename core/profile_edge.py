"""Profile min-edge resolution — standalone to avoid import-order issues in GUI."""

from __future__ import annotations

from typing import Any

_PROFILE_MIN_EDGE_BY_NAME: dict[str, float] = {
    "safe": 0.12,
    "high_volatility": 0.13,
    "thin_liquidity": 0.11,
    "tight_spread": 0.08,
}


def profile_min_edge_pct(profile: Any) -> float:
    """Return profile min edge; safe if Streamlit/engine cached an older Profile class."""
    if hasattr(profile, "min_edge_pct"):
        return float(profile.min_edge_pct)
    name = str(getattr(profile, "name", "") or "")
    if name in _PROFILE_MIN_EDGE_BY_NAME:
        return _PROFILE_MIN_EDGE_BY_NAME[name]
    legacy_mult = float(getattr(profile, "min_edge_mult", 1.0))
    return 0.10 * legacy_mult
