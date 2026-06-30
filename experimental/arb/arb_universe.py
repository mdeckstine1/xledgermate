"""Multi-pair XRPL arb universe monitor (read-only)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from experimental.arb.book_provider import fetch_stable_cross_book_mid_sync, fetch_token_xrp_book_mid_sync
from experimental.arb.clob_amm_monitor import (
    DEFAULT_DISLOCATION_BPS,
    augment_clob_amm_row,
    estimate_arb_costs_bps,
    net_edge_bps,
    spread_bps,
)
from experimental.liquidity.amm_provider import fetch_amm_info_sync

logger = logging.getLogger(__name__)

ARB_UNIVERSE_LOG = Path("logs/arb_universe.jsonl")

USDC_ISSUER = "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE"
USDC_CURRENCY = "5553444300000000000000000000000000000000"
USD_ISSUER = "rvYAfWj5gh67oV6fW32ZzP3Aw4Eubs59B"
USD_CURRENCY = "USD"

# 2-leg stable basis: two CLOB half-spreads + slippage (no AMM on direct leg)
STABLE_BASIS_COST_BPS = 12.0


def _pair_clob_amm(
    *,
    pair_id: str,
    label: str,
    rpc_url: str,
    currency: str,
    issuer: str,
    clob_mid: Optional[float],
    clob_spread_pct: Optional[float],
    dislocation_bps: float = DEFAULT_DISLOCATION_BPS,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": pair_id,
        "label": label,
        "kind": "clob_amm",
        "clob_mid_stable_per_xrp": clob_mid,
        "amm_mid_stable_per_xrp": None,
        "spread_bps": None,
        "dislocation": False,
        "net_edge_bps": None,
        "net_positive": False,
        "status": "no_clob_mid",
    }
    if clob_spread_pct is not None:
        row["clob_spread_pct"] = round(float(clob_spread_pct), 4)

    amm = fetch_amm_info_sync(rpc_url=rpc_url, rlusd_issuer=issuer, rlusd_currency=currency)
    if not amm:
        row["status"] = "amm_unavailable"
        return row

    amm_mid = amm.get("mid")
    row["amm_mid_stable_per_xrp"] = amm_mid
    if amm.get("trading_fee_bps") is not None:
        row["amm_fee_bps"] = amm.get("trading_fee_bps")

    if clob_mid is None or not amm_mid:
        row["status"] = "amm_unavailable" if not amm_mid else "no_clob_mid"
        return row

    gross = spread_bps(float(clob_mid), float(amm_mid))
    row["spread_bps"] = round(gross, 2) if gross is not None else None
    row["dislocation"] = bool(gross is not None and gross >= dislocation_bps)
    costs = estimate_arb_costs_bps(
        clob_spread_pct=clob_spread_pct,
        amm_fee_bps=row.get("amm_fee_bps"),
    )
    row.update(costs)
    net = net_edge_bps(gross, costs["total_cost_bps"])
    row["net_edge_bps"] = net
    row["net_positive"] = bool(net is not None and net > 0)
    row["status"] = "ok"
    return row


def refresh_arb_universe(
    *,
    rpc_url: str,
    rlusd_currency: str,
    rlusd_issuer: str,
    rlusd_clob_mid: Optional[float],
    rlusd_spread_pct: Optional[float],
    dislocation_bps: float = DEFAULT_DISLOCATION_BPS,
    path: Path = ARB_UNIVERSE_LOG,
) -> Dict[str, Any]:
    """Poll all arb candidate pairs; append JSONL snapshot."""
    pairs: List[Dict[str, Any]] = []

    pairs.append(
        _pair_clob_amm(
            pair_id="rlusd_xrp",
            label="RLUSD/XRP",
            rpc_url=rpc_url,
            currency=rlusd_currency,
            issuer=rlusd_issuer,
            clob_mid=rlusd_clob_mid,
            clob_spread_pct=rlusd_spread_pct,
            dislocation_bps=dislocation_bps,
        )
    )

    usdc_book = fetch_token_xrp_book_mid_sync(
        rpc_url=rpc_url, currency=USDC_CURRENCY, issuer=USDC_ISSUER
    )
    pairs.append(
        _pair_clob_amm(
            pair_id="usdc_xrp",
            label="USDC/XRP",
            rpc_url=rpc_url,
            currency=USDC_CURRENCY,
            issuer=USDC_ISSUER,
            clob_mid=usdc_book.get("mid"),
            clob_spread_pct=usdc_book.get("spread_pct"),
            dislocation_bps=dislocation_bps,
        )
    )

    usd_book = fetch_token_xrp_book_mid_sync(
        rpc_url=rpc_url, currency=USD_CURRENCY, issuer=USD_ISSUER
    )
    pairs.append(
        _pair_clob_amm(
            pair_id="usd_xrp",
            label="USD/XRP (Bitstamp)",
            rpc_url=rpc_url,
            currency=USD_CURRENCY,
            issuer=USD_ISSUER,
            clob_mid=usd_book.get("mid"),
            clob_spread_pct=usd_book.get("spread_pct"),
            dislocation_bps=dislocation_bps,
        )
    )

    rl = pairs[0]
    us = pairs[1]
    rl_mid = rl.get("amm_mid_stable_per_xrp") or rl.get("clob_mid_stable_per_xrp")
    us_mid = us.get("amm_mid_stable_per_xrp") or us.get("clob_mid_stable_per_xrp")
    implied = None
    if rl_mid and us_mid and float(us_mid) > 0:
        implied = float(rl_mid) / float(us_mid)

    direct = fetch_stable_cross_book_mid_sync(
        rpc_url=rpc_url,
        base_currency=rlusd_currency,
        base_issuer=rlusd_issuer,
        quote_currency=USDC_CURRENCY,
        quote_issuer=USDC_ISSUER,
    )
    direct_mid = direct.get("mid")
    peg_bps = None
    cross_direct_bps = None
    if implied and implied > 0:
        peg_bps = round((implied - 1.0) * 10_000.0, 2)
    if implied and direct_mid and implied > 0:
        cross_direct_bps = round((float(direct_mid) - implied) / implied * 10_000.0, 2)

    gross_basis = abs(cross_direct_bps) if cross_direct_bps is not None else (
        abs(peg_bps) if peg_bps is not None else None
    )
    net_basis = (
        round(float(gross_basis) - STABLE_BASIS_COST_BPS, 2)
        if gross_basis is not None
        else None
    )

    basis_row = {
        "id": "rlusd_usdc_basis",
        "label": "RLUSD/USDC basis",
        "kind": "stable_basis",
        "implied_rlusd_per_usdc": round(implied, 6) if implied else None,
        "direct_rlusd_per_usdc": round(float(direct_mid), 6) if direct_mid else None,
        "peg_deviation_bps": peg_bps,
        "cross_vs_direct_bps": cross_direct_bps,
        "spread_bps": gross_basis,
        "net_edge_bps": net_basis,
        "net_positive": bool(net_basis is not None and net_basis > 0),
        "status": "ok" if implied else "incomplete",
        "note": "Implied via XRP AMM mids; direct from RLUSD/USDC book",
    }
    pairs.append(basis_row)

    net_positive = [p for p in pairs if p.get("net_positive")]
    snapshot = {
        "kind": "arb_universe",
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "pairs": pairs,
        "best_net": max((float(p["net_edge_bps"]) for p in pairs if p.get("net_edge_bps") is not None), default=None),
        "net_positive_count": len(net_positive),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, separators=(",", ":")) + "\n")
    return snapshot


def tail_universe_records(*, limit: int = 96, path: Path = ARB_UNIVERSE_LOG) -> List[Dict[str, Any]]:
    if not path.is_file() or limit <= 0:
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


def format_universe_report(*, logs_dir: Optional[Path] = None, limit: int = 48) -> str:
    logs = logs_dir or Path("logs")
    rows = tail_universe_records(limit=limit, path=logs / "arb_universe.jsonl")
    lines = [
        "=== XRPL arb universe soak ===",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"samples: {len(rows)}",
        "",
        "Pairs monitored: RLUSD/XRP, USDC/XRP, USD/XRP (Bitstamp), RLUSD/USDC basis",
        "",
    ]
    if not rows:
        lines.append("No arb_universe.jsonl yet.")
        return "\n".join(lines)

    latest = rows[-1]
    lines.append(f"latest: {latest.get('ts_utc', '')[:19]} UTC | NET+ pairs: {latest.get('net_positive_count')}")
    lines.append("")
    for p in latest.get("pairs") or []:
        if p.get("kind") == "stable_basis":
            lines.append(
                f"  {p.get('label')}: implied={p.get('implied_rlusd_per_usdc')} "
                f"direct={p.get('direct_rlusd_per_usdc')} peg={p.get('peg_deviation_bps')}bps "
                f"cross-direct={p.get('cross_vs_direct_bps')}bps net={p.get('net_edge_bps')}bps"
            )
        else:
            lines.append(
                f"  {p.get('label')}: gross={p.get('spread_bps')}bps net={p.get('net_edge_bps')}bps "
                f"NET+={p.get('net_positive')} ({p.get('status')})"
            )
    lines.append("")
    return "\n".join(lines)
