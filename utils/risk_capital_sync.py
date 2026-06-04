"""Align configured risk capital with live bot wallet."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple


def live_portfolio_xrp(runtime: Mapping[str, Any]) -> Optional[float]:
    value = runtime.get("portfolio_value_xrp")
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def risk_capital_mismatch_pct(
    configured_xrp: float,
    live_xrp: float,
) -> float:
    """Percent difference vs live portfolio (0 if aligned)."""
    if live_xrp <= 0:
        return 0.0
    return abs(configured_xrp - live_xrp) / live_xrp * 100.0


def suggest_risk_capital_sync(
    runtime: Mapping[str, Any],
    configured_xrp: float,
    *,
    warn_threshold_pct: float = 15.0,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Returns (suggested_xrp, warning_message).
    Suggested value is live portfolio when mismatch exceeds threshold.
    """
    live = live_portfolio_xrp(runtime)
    if live is None:
        return None, None
    mismatch = risk_capital_mismatch_pct(configured_xrp, live)
    if mismatch < warn_threshold_pct:
        return None, None
    return live, (
        f"Risk capital {configured_xrp:.1f} XRP vs live portfolio {live:.1f} XRP "
        f"({mismatch:.0f}% off) — sync so order size caps match the wallet."
    )
