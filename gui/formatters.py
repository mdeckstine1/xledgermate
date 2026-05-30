"""Shared GUI formatting helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def fmt_price(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def fmt_xrp_balance(value: Any) -> str:
    return f"{float(value or 0):,.2f}"


def fmt_rlusd_balance(value: Any) -> str:
    return f"{float(value or 0):,.4f}"


def portfolio_value_rlusd(runtime: dict) -> Optional[float]:
    port_xrp = runtime.get("portfolio_value_xrp")
    mid = runtime.get("mid_price")
    if port_xrp is not None and mid is not None and float(mid) > 0:
        return float(port_xrp) * float(mid)
    xrp = runtime.get("balance_xrp")
    rlusd = runtime.get("balance_rlusd")
    if xrp is None or rlusd is None or mid is None or float(mid) <= 0:
        return None
    return float(rlusd) + float(xrp) * float(mid)


def session_pnl_from_runtime(runtime: dict) -> tuple[float, float]:
    port = runtime.get("portfolio_value_xrp")
    baseline_port = runtime.get("session_baseline_portfolio_xrp")
    if runtime.get("session_pnl_mtm_xrp") is not None:
        mtm = float(runtime["session_pnl_mtm_xrp"])
    elif port is not None and baseline_port is not None:
        mtm = float(port) - float(baseline_port)
    else:
        mtm = float(runtime.get("session_pnl_xrp_estimate", 0.0))

    if runtime.get("session_pnl_balance_xrp") is not None:
        balance = float(runtime["session_pnl_balance_xrp"])
    else:
        balance = float(runtime.get("session_pnl_xrp_estimate", 0.0))
    return mtm, balance


def balance_value_shares(runtime: dict, *, mid: float) -> tuple[Optional[float], Optional[float]]:
    """Portfolio share by value at mid: (xrp_fraction, rlusd_fraction)."""
    xrp = runtime.get("balance_xrp")
    rlusd = runtime.get("balance_rlusd")
    if xrp is None and rlusd is None:
        return None, None
    xrp_f = float(xrp or 0)
    rlusd_f = float(rlusd or 0)
    use_mid = mid if mid > 0 else float(runtime.get("mid_price") or 0)
    if use_mid <= 0:
        return None, None
    total_xrp = xrp_f + (rlusd_f / use_mid)
    if total_xrp <= 0:
        return 0.0, 0.0
    xrp_share = xrp_f / total_xrp
    rlusd_share = (rlusd_f / use_mid) / total_xrp
    return xrp_share, rlusd_share


def fmt_balance_with_share(amount: str, share: Optional[float]) -> str:
    if share is None:
        return amount
    return f"{amount} · {share:.0%}"


def inventory_ratio(runtime: dict, *, mid: float) -> Optional[float]:
    xrp = runtime.get("balance_xrp")
    rlusd = runtime.get("balance_rlusd")
    if xrp is None and rlusd is None:
        return None
    xrp_f = float(xrp or 0)
    rlusd_f = float(rlusd or 0)
    use_mid = mid if mid > 0 else float(runtime.get("mid_price") or 0)
    total = xrp_f + (rlusd_f / use_mid if use_mid > 0 else 0)
    return (xrp_f / total) if total > 0 else 0.0


def clean_decisions_table(runtime: dict, *, limit: int = 12) -> pd.DataFrame:
    """Flatten recent decision events into a readable operator table."""
    rows: List[Dict[str, str]] = []
    for item in runtime.get("recent_decisions") or []:
        if not isinstance(item, dict):
            continue
        ts = str(item.get("ts_utc", ""))[:19].replace("T", " ")
        cat = str(item.get("category", ""))
        msg = str(item.get("message", ""))
        if len(msg) > 120:
            msg = msg[:117] + "…"
        rows.append({"Time (UTC)": ts, "Type": cat, "Message": msg})
        if len(rows) >= limit:
            break
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["Time (UTC)", "Type", "Message"])
