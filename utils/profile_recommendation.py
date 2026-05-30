"""Profile recommendation helpers (utils/ avoids stale core/ bytecode on GUI reload)."""

from __future__ import annotations

from typing import Tuple

# Never suggest or auto-switch to profit_mode — manual selection only.
AUTO_SWITCH_PROFILES = frozenset(
    {"safe", "high_volatility", "thin_liquidity", "tight_spread"}
)


def normalize_profile_recommendation(profile: str, reason: str) -> Tuple[str, str]:
    """Map legacy profit_mode suggestions to tight_spread (profit is manual-only)."""
    name = (profile or "safe").strip().lower()
    if name == "profit_mode":
        return (
            "tight_spread",
            "Ideal competitive book — Tight spread is recommended; "
            "select Profit mode manually only if you want maximum aggression.",
        )
    return name, reason or ""
