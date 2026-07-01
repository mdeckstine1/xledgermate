"""H1 read-only CLOB vs AMM dislocation monitor (no trades)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from experimental.liquidity.amm_provider import fetch_amm_info_sync

logger = logging.getLogger(__name__)

CLOB_AMM_LOG = Path("logs/clob_amm_spread.jsonl")
DEFAULT_DISLOCATION_BPS = 8.0
DEFAULT_SLIPPAGE_BUFFER_BPS = 2.0
DEFAULT_AMM_FEE_FALLBACK_BPS = 10.0
DEFAULT_CLOB_HALF_SPREAD_FALLBACK_BPS = 5.0


def spread_bps(clob_mid: float, amm_mid: float) -> Optional[float]:
    if clob_mid <= 0 or amm_mid <= 0:
        return None
    ref = (clob_mid + amm_mid) / 2.0
    if ref <= 0:
        return None
    return abs(clob_mid - amm_mid) / ref * 10_000.0


def clob_half_spread_bps(spread_pct: Optional[float]) -> float:
    """Book spread_pct is full L1 width in percent (0.1 = 0.1%). Half ≈ spread_pct × 50 bps."""
    if spread_pct is None:
        return DEFAULT_CLOB_HALF_SPREAD_FALLBACK_BPS
    try:
        pct = float(spread_pct)
    except (TypeError, ValueError):
        return DEFAULT_CLOB_HALF_SPREAD_FALLBACK_BPS
    if pct <= 0:
        return DEFAULT_CLOB_HALF_SPREAD_FALLBACK_BPS
    return round(pct * 50.0, 2)


def estimate_arb_costs_bps(
    *,
    clob_spread_pct: Optional[float] = None,
    amm_fee_bps: Optional[float] = None,
    slippage_buffer_bps: float = DEFAULT_SLIPPAGE_BUFFER_BPS,
    amm_fee_fallback_bps: float = DEFAULT_AMM_FEE_FALLBACK_BPS,
) -> Dict[str, float]:
    half = clob_half_spread_bps(clob_spread_pct)
    amm = float(amm_fee_bps) if amm_fee_bps is not None else amm_fee_fallback_bps
    slip = float(slippage_buffer_bps)
    total = round(half + amm + slip, 2)
    return {
        "clob_half_spread_bps": half,
        "amm_fee_bps": round(amm, 2),
        "slippage_buffer_bps": round(slip, 2),
        "total_cost_bps": total,
    }


def net_edge_bps(gross_spread_bps: Optional[float], total_cost_bps: float) -> Optional[float]:
    if gross_spread_bps is None:
        return None
    return round(float(gross_spread_bps) - float(total_cost_bps), 2)


def augment_clob_amm_row(
    row: Dict[str, Any],
    *,
    default_clob_spread_pct: Optional[float] = None,
    slippage_buffer_bps: float = DEFAULT_SLIPPAGE_BUFFER_BPS,
) -> Dict[str, Any]:
    """Add net-edge fields to a snapshot row (idempotent)."""
    out = dict(row)
    if out.get("net_edge_bps") is not None and out.get("total_cost_bps") is not None:
        return out
    spread_pct = out.get("clob_spread_pct")
    if spread_pct is None:
        spread_pct = default_clob_spread_pct
    costs = estimate_arb_costs_bps(
        clob_spread_pct=spread_pct,
        amm_fee_bps=out.get("amm_fee_bps"),
        slippage_buffer_bps=float(out.get("slippage_buffer_bps") or slippage_buffer_bps),
    )
    out.update(costs)
    out["slippage_buffer_bps"] = costs["slippage_buffer_bps"]
    if spread_pct is not None:
        out["clob_spread_pct"] = spread_pct
    gross = out.get("spread_bps")
    net = net_edge_bps(gross, costs["total_cost_bps"])
    out["net_edge_bps"] = net
    out["net_positive"] = bool(net is not None and net > 0)
    return out


def append_clob_amm_record(record: Dict[str, Any], path: Path = CLOB_AMM_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record)
    row.setdefault("ts_utc", datetime.now(tz=timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def tail_clob_amm_records(*, limit: int = 100, path: Path = CLOB_AMM_LOG) -> List[Dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def summarize_clob_amm_rows(
    rows: List[Dict[str, Any]],
    *,
    default_clob_spread_pct: Optional[float] = None,
    slippage_buffer_bps: float = DEFAULT_SLIPPAGE_BUFFER_BPS,
) -> Dict[str, Any]:
    enriched = [
        augment_clob_amm_row(
            r,
            default_clob_spread_pct=default_clob_spread_pct,
            slippage_buffer_bps=slippage_buffer_bps,
        )
        for r in rows
    ]
    if not enriched:
        return {
            "samples": 0,
            "dislocation_count": 0,
            "dislocation_pct": 0.0,
            "net_positive_count": 0,
            "net_positive_pct": 0.0,
            "max_spread_bps": None,
            "avg_spread_bps": None,
            "max_net_edge_bps": None,
            "avg_net_edge_bps": None,
            "avg_total_cost_bps": None,
        }
    gross_vals = [float(r["spread_bps"]) for r in enriched if r.get("spread_bps") is not None]
    net_vals = [float(r["net_edge_bps"]) for r in enriched if r.get("net_edge_bps") is not None]
    cost_vals = [float(r["total_cost_bps"]) for r in enriched if r.get("total_cost_bps") is not None]
    disloc = sum(1 for r in enriched if r.get("dislocation"))
    net_pos = sum(1 for r in enriched if r.get("net_positive"))
    n = len(enriched)
    return {
        "samples": n,
        "dislocation_count": disloc,
        "dislocation_pct": round(disloc / n * 100.0, 1),
        "net_positive_count": net_pos,
        "net_positive_pct": round(net_pos / n * 100.0, 1),
        "max_spread_bps": round(max(gross_vals), 2) if gross_vals else None,
        "avg_spread_bps": round(sum(gross_vals) / len(gross_vals), 2) if gross_vals else None,
        "max_net_edge_bps": round(max(net_vals), 2) if net_vals else None,
        "avg_net_edge_bps": round(sum(net_vals) / len(net_vals), 2) if net_vals else None,
        "avg_total_cost_bps": round(sum(cost_vals) / len(cost_vals), 2) if cost_vals else None,
    }


def record_clob_amm_snapshot(
    *,
    clob_mid: Optional[float],
    rpc_url: str,
    rlusd_issuer: str,
    rlusd_currency: str = "RLUSD",
    clob_spread_pct: Optional[float] = None,
    dislocation_bps: float = DEFAULT_DISLOCATION_BPS,
    slippage_buffer_bps: float = DEFAULT_SLIPPAGE_BUFFER_BPS,
    path: Path = CLOB_AMM_LOG,
    book_depth_limit: int = 20,
    capture_fill_depth: bool = True,
) -> Dict[str, Any]:
    """Fetch AMM mid + fee, log spread/net edge, return HUD fields."""
    row: Dict[str, Any] = {
        "kind": "clob_amm",
        "clob_mid_rlusd_per_xrp": clob_mid,
        "amm_mid_rlusd_per_xrp": None,
        "spread_bps": None,
        "dislocation": False,
        "status": "no_clob_mid",
    }
    if clob_mid is None or float(clob_mid) <= 0:
        return row

    if clob_spread_pct is not None:
        row["clob_spread_pct"] = round(float(clob_spread_pct), 4)

    amm_info = fetch_amm_info_sync(
        rpc_url=rpc_url,
        rlusd_issuer=rlusd_issuer,
        rlusd_currency=rlusd_currency,
    )
    if not amm_info:
        row["status"] = "amm_unavailable"
        append_clob_amm_record(row, path=path)
        return row

    amm_mid = amm_info.get("mid")
    row["amm_mid_rlusd_per_xrp"] = amm_mid
    if amm_info.get("trading_fee") is not None:
        row["amm_trading_fee"] = amm_info.get("trading_fee")
    if amm_info.get("trading_fee_bps") is not None:
        row["amm_fee_bps"] = amm_info.get("trading_fee_bps")
    if amm_info.get("xrp_reserve") is not None:
        row["amm_xrp_reserve"] = round(float(amm_info["xrp_reserve"]), 6)
    if amm_info.get("rlusd_reserve") is not None:
        row["amm_rlusd_reserve"] = round(float(amm_info["rlusd_reserve"]), 6)

    if capture_fill_depth:
        try:
            from experimental.arb.book_provider import (
                book_depth_to_json,
                fetch_token_xrp_book_depth_sync,
            )

            depth = fetch_token_xrp_book_depth_sync(
                rpc_url=rpc_url,
                currency=rlusd_currency,
                issuer=rlusd_issuer,
                limit=book_depth_limit,
            )
            row["book_depth"] = book_depth_to_json(depth)
            if clob_spread_pct is None and depth.spread_pct is not None:
                row["clob_spread_pct"] = round(float(depth.spread_pct), 4)
        except Exception as exc:
            logger.debug("book_depth capture failed: %s", exc)

    if amm_mid is None:
        row["status"] = "amm_unavailable"
        append_clob_amm_record(row, path=path)
        return row

    bps = spread_bps(float(clob_mid), float(amm_mid))
    row["spread_bps"] = round(bps, 2) if bps is not None else None
    row["dislocation"] = bool(bps is not None and bps >= dislocation_bps)
    row["status"] = "ok"
    row["slippage_buffer_bps"] = slippage_buffer_bps
    row = augment_clob_amm_row(row, slippage_buffer_bps=slippage_buffer_bps)
    append_clob_amm_record(row, path=path)
    return row


def latest_hud_fields(path: Path = CLOB_AMM_LOG) -> Dict[str, Any]:
    rows = tail_clob_amm_records(limit=1, path=path)
    if not rows:
        return {
            "clob_amm_spread_bps": None,
            "clob_amm_dislocation": False,
            "clob_amm_monitor_status": "no_data",
            "clob_amm_monitor_display": "—",
            "clob_amm_net_edge_bps": None,
        }
    last = augment_clob_amm_row(rows[-1])
    bps = last.get("spread_bps")
    net = last.get("net_edge_bps")
    status = str(last.get("status") or "unknown")
    disloc = bool(last.get("dislocation"))
    display = "—"
    if bps is not None:
        display = f"{float(bps):.1f} bps"
        if net is not None:
            display += f" / net {float(net):+.1f}"
        display += " ⚡" if disloc else ""
    elif status == "amm_unavailable":
        display = "AMM n/a"
    return {
        "clob_amm_spread_bps": bps,
        "clob_amm_dislocation": disloc,
        "clob_amm_monitor_status": status,
        "clob_amm_clob_mid": last.get("clob_mid_rlusd_per_xrp"),
        "clob_amm_amm_mid": last.get("amm_mid_rlusd_per_xrp"),
        "clob_amm_net_edge_bps": net,
        "clob_amm_monitor_display": display,
    }


def format_clob_amm_report(
    *,
    logs_dir: Optional[Path] = None,
    limit: int = 288,
    default_clob_spread_pct: Optional[float] = None,
) -> str:
    """Soak report: gross + net edge, cost model, recent samples."""
    logs = logs_dir or Path("logs")
    path = logs / "clob_amm_spread.jsonl"
    rows = tail_clob_amm_records(limit=limit, path=path)
    enriched = [
        augment_clob_amm_row(r, default_clob_spread_pct=default_clob_spread_pct)
        for r in rows
    ]
    summary = summarize_clob_amm_rows(enriched)
    costs = estimate_arb_costs_bps(clob_spread_pct=default_clob_spread_pct)
    lines = [
        "=== CLOB vs AMM soak report (read-only) ===",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"path: {path}",
        f"samples_in_window: {summary['samples']} (tail limit {limit})",
        "",
        "--- Cost model (estimated round-trip) ---",
        f"  CLOB half-spread:  {costs['clob_half_spread_bps']:.2f} bps"
        + (" (from latest Alpha book)" if default_clob_spread_pct is not None else " (fallback)"),
        f"  AMM trading fee:   per-sample from pool TradingFee (fallback {DEFAULT_AMM_FEE_FALLBACK_BPS:.0f} bps)",
        f"  Slippage buffer:   {DEFAULT_SLIPPAGE_BUFFER_BPS:.2f} bps",
        f"  Typical total:     ~{costs['total_cost_bps']:.2f} bps when book spread unknown",
        "",
        "  net_edge_bps = gross_spread_bps − clob_half − amm_fee − slippage_buffer",
        "",
        "--- Summary ---",
        f"gross dislocations (>={DEFAULT_DISLOCATION_BPS:.0f} bps): {summary['dislocation_count']}/{summary['samples']} ({summary['dislocation_pct']}%)",
        f"net positive (edge > 0 after costs): {summary['net_positive_count']}/{summary['samples']} ({summary['net_positive_pct']}%)",
    ]
    if summary["max_spread_bps"] is not None:
        lines.append(
            f"gross spread: max {summary['max_spread_bps']:.2f} bps · avg {summary['avg_spread_bps']:.2f} bps"
        )
    if summary["max_net_edge_bps"] is not None:
        lines.append(
            f"net edge:     max {summary['max_net_edge_bps']:+.2f} bps · avg {summary['avg_net_edge_bps']:+.2f} bps"
        )
    if summary["avg_total_cost_bps"] is not None:
        lines.append(f"avg est cost: {summary['avg_total_cost_bps']:.2f} bps")
    lines.extend(["", "--- Recent samples ---", ""])
    if not enriched:
        lines.append("No clob_amm_spread.jsonl yet — Alpha HUD arb monitor polls every ~60s.")
        return "\n".join(lines)

    for row in enriched[-30:]:
        ts = (row.get("ts_utc") or "")[:19].replace("T", " ")
        gross = row.get("spread_bps")
        net = row.get("net_edge_bps")
        flag = "NET+" if row.get("net_positive") else ("DISLOC" if row.get("dislocation") else "ok")
        cost = row.get("total_cost_bps")
        lines.append(
            f"[{ts}] clob={row.get('clob_mid_rlusd_per_xrp')} amm={row.get('amm_mid_rlusd_per_xrp')} "
            f"gross={gross} net={net} cost={cost} {flag} ({row.get('status')})"
        )
    return "\n".join(lines)
