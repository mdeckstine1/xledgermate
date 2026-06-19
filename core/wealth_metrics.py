"""RLUSD-stable wealth metrics for operator HUD (RLUSD ≈ $1)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _f(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def wealth_rlusd(
    *,
    balance_xrp: float,
    balance_rlusd: float,
    mid_rlusd_per_xrp: float,
) -> float:
    """Total book value in RLUSD-stable terms: RLUSD cash + XRP marked at mid."""
    if mid_rlusd_per_xrp <= 0:
        return float(balance_rlusd)
    return float(balance_rlusd) + float(balance_xrp) * float(mid_rlusd_per_xrp)


def compute_wealth_metrics(runtime: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """
    Session wealth in RLUSD-stable terms with skim vs spot decomposition.

    Returns keys suitable for HUD /state JSON (None when inputs missing).
    """
    mid = _f(runtime.get("mid_price") or runtime.get("mid_rlusd_per_xrp"))
    xrp = _f(runtime.get("balance_xrp"))
    rlusd = _f(runtime.get("balance_rlusd"))
    bx = _f(runtime.get("session_baseline_xrp"))
    br = _f(runtime.get("session_baseline_rlusd"))
    bm = _f(runtime.get("session_baseline_mid"))

    out: Dict[str, Optional[float]] = {
        "wealth_rlusd": None,
        "wealth_baseline_rlusd": None,
        "wealth_delta_session_rlusd": None,
        "skim_delta_rlusd": None,
        "spot_delta_rlusd": None,
        "rebalance_delta_rlusd": None,
        "xrp_value_rlusd": None,
        "rlusd_stable_balance": None,
        "xrp_share_pct": None,
    }

    if mid is None or mid <= 0 or xrp is None or rlusd is None:
        return out

    w_now = wealth_rlusd(balance_xrp=xrp, balance_rlusd=rlusd, mid_rlusd_per_xrp=mid)
    out["wealth_rlusd"] = round(w_now, 4)
    out["rlusd_stable_balance"] = round(rlusd, 4)
    out["xrp_value_rlusd"] = round(xrp * mid, 4)

    total = xrp + (rlusd / mid)
    if total > 0:
        out["xrp_share_pct"] = round(100.0 * xrp / total, 1)

    skim_xrp = _f(runtime.get("session_spread_capture_xrp")) or 0.0
    out["skim_delta_rlusd"] = round(skim_xrp * mid, 6)

    if bx is not None and br is not None and bm is not None and bm > 0:
        w_base = wealth_rlusd(balance_xrp=bx, balance_rlusd=br, mid_rlusd_per_xrp=bm)
        out["wealth_baseline_rlusd"] = round(w_base, 4)
        delta = w_now - w_base
        out["wealth_delta_session_rlusd"] = round(delta, 4)
        # XRP held at session start × mid move (spot P&L on inventory beta)
        spot = bx * (mid - bm)
        out["spot_delta_rlusd"] = round(spot, 4)
        # Residual: balance changes (trades, fees) not explained by skim or spot alone
        reb = delta - skim_xrp * mid - spot
        out["rebalance_delta_rlusd"] = round(reb, 4)

    return out


def enrich_runtime_wealth(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """Attach wealth_* fields to runtime dict for HUD consumers."""
    metrics = compute_wealth_metrics(runtime)
    for key, val in metrics.items():
        if val is not None:
            runtime[key] = val
    return runtime
