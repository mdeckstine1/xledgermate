"""Align configured risk capital with live bot wallet."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple


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


def build_risk_capital_snapshot(
    config: Any,
    *,
    portfolio_xrp_equiv: float,
    mid_rlusd_per_xrp: Optional[float] = None,
) -> Dict[str, Any]:
    """HUD / SKYNET — configured vs effective risk capital and leg cap."""
    configured = float(config.risk_capital_xrp)
    sync = bool(getattr(config, "alpha_risk_capital_sync_portfolio", True))
    effective = float(
        config.effective_risk_capital_xrp(
            mid_rlusd_per_xrp,
            portfolio_xrp_equiv=portfolio_xrp_equiv,
        )
    )
    leg_pct = float(getattr(config, "max_leg_size_pct_of_capital", 0.12) or 0.12)
    risk_pct = float(getattr(config, "alpha_risk_per_trade_pct", 0.5) or 0.5)
    risk_cap_xrp = (
        portfolio_xrp_equiv * (risk_pct / 100.0) if portfolio_xrp_equiv > 0 and risk_pct > 0 else 0.0
    )
    leg_cap_xrp = effective * leg_pct
    binding = "risk_per_trade_pct"
    if risk_cap_xrp > 0 and leg_cap_xrp > 0:
        if leg_cap_xrp < risk_cap_xrp * 0.999:
            binding = "leg_cap"
        else:
            binding = "risk_per_trade_pct"
    mismatch_pct = risk_capital_mismatch_pct(configured, portfolio_xrp_equiv) if portfolio_xrp_equiv > 0 else 0.0
    return {
        "configured_xrp": round(configured, 2),
        "effective_xrp": round(effective, 2),
        "portfolio_xrp_equiv": round(float(portfolio_xrp_equiv), 2),
        "sync_portfolio": sync,
        "mismatch_pct": round(mismatch_pct, 1),
        "leg_cap_xrp": round(leg_cap_xrp, 4),
        "risk_cap_xrp": round(risk_cap_xrp, 4),
        "risk_per_trade_pct": risk_pct,
        "binding_cap": binding,
        "needs_sync": sync and mismatch_pct >= 15.0 and effective >= portfolio_xrp_equiv * 0.99,
    }


def format_risk_capital_context_block(snap: Dict[str, Any]) -> str:
    if not snap:
        return "=== Risk capital (sizing) ===\n(unavailable)"
    return "\n".join(
        [
            "=== Risk capital (sizing — leg_cap uses effective, clip uses risk_per_trade_pct) ===",
            f"configured_xrp={snap.get('configured_xrp')} effective_xrp={snap.get('effective_xrp')} "
            f"portfolio={snap.get('portfolio_xrp_equiv')} sync_portfolio={snap.get('sync_portfolio')}",
            f"risk_per_trade_pct={snap.get('risk_per_trade_pct')}% → risk_cap_xrp={snap.get('risk_cap_xrp')} "
            f"(usual clip binder)",
            f"leg_cap_xrp={snap.get('leg_cap_xrp')} (effective × max_leg_size_pct)",
            f"binding_cap={snap.get('binding_cap')} mismatch_pct={snap.get('mismatch_pct')}",
            "When sync_portfolio=true, effective=max(configured, portfolio) — yaml drift does not under-size leg_cap.",
            "To grow clips: raise alpha_risk_per_trade_pct (and max_pending_buys), not just risk_capital.",
        ]
    )
