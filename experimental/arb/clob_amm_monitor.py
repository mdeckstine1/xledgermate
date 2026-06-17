"""H1 read-only CLOB vs AMM dislocation monitor (no trades)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from experimental.liquidity.amm_provider import fetch_amm_implied_mid_sync

logger = logging.getLogger(__name__)

CLOB_AMM_LOG = Path("logs/clob_amm_spread.jsonl")
DEFAULT_DISLOCATION_BPS = 8.0


def spread_bps(clob_mid: float, amm_mid: float) -> Optional[float]:
    if clob_mid <= 0 or amm_mid <= 0:
        return None
    ref = (clob_mid + amm_mid) / 2.0
    if ref <= 0:
        return None
    return abs(clob_mid - amm_mid) / ref * 10_000.0


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


def record_clob_amm_snapshot(
    *,
    clob_mid: Optional[float],
    rpc_url: str,
    rlusd_issuer: str,
    rlusd_currency: str = "RLUSD",
    dislocation_bps: float = DEFAULT_DISLOCATION_BPS,
    path: Path = CLOB_AMM_LOG,
) -> Dict[str, Any]:
    """Fetch AMM mid, log spread, return HUD fields."""
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

    amm_mid = fetch_amm_implied_mid_sync(
        rpc_url=rpc_url,
        rlusd_issuer=rlusd_issuer,
        rlusd_currency=rlusd_currency,
    )
    row["amm_mid_rlusd_per_xrp"] = amm_mid
    if amm_mid is None:
        row["status"] = "amm_unavailable"
        append_clob_amm_record(row, path=path)
        return row

    bps = spread_bps(float(clob_mid), float(amm_mid))
    row["spread_bps"] = round(bps, 2) if bps is not None else None
    row["dislocation"] = bool(bps is not None and bps >= dislocation_bps)
    row["status"] = "ok"
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
        }
    last = rows[-1]
    bps = last.get("spread_bps")
    status = str(last.get("status") or "unknown")
    disloc = bool(last.get("dislocation"))
    display = "—"
    if bps is not None:
        display = f"{float(bps):.1f} bps" + (" ⚡" if disloc else "")
    elif status == "amm_unavailable":
        display = "AMM n/a"
    return {
        "clob_amm_spread_bps": bps,
        "clob_amm_dislocation": disloc,
        "clob_amm_monitor_status": status,
        "clob_amm_clob_mid": last.get("clob_mid_rlusd_per_xrp"),
        "clob_amm_amm_mid": last.get("amm_mid_rlusd_per_xrp"),
        "clob_amm_monitor_display": display,
    }


def format_clob_amm_report(*, logs_dir: Optional[Path] = None, limit: int = 48) -> str:
    logs = logs_dir or Path("logs")
    path = logs / "clob_amm_spread.jsonl"
    rows = tail_clob_amm_records(limit=limit, path=path)
    lines = [
        "=== CLOB vs AMM monitor (H1 read-only) ===",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"path: {path}",
        f"samples: {len(rows)}",
        "",
    ]
    if not rows:
        lines.append("No clob_amm_spread.jsonl yet — ws-hud monitor polls every ~60s.")
        return "\n".join(lines)

    disloc_count = sum(1 for r in rows if r.get("dislocation"))
    bps_vals = [float(r["spread_bps"]) for r in rows if r.get("spread_bps") is not None]
    max_bps = max(bps_vals) if bps_vals else None
    lines.append(f"dislocations (>={DEFAULT_DISLOCATION_BPS:.0f} bps): {disloc_count}/{len(rows)}")
    if max_bps is not None:
        lines.append(f"max spread: {max_bps:.2f} bps")
    lines.append("")
    for row in rows[-20:]:
        ts = (row.get("ts_utc") or "")[:19].replace("T", " ")
        bps = row.get("spread_bps")
        flag = "DISLOC" if row.get("dislocation") else "ok"
        lines.append(
            f"[{ts}] clob={row.get('clob_mid_rlusd_per_xrp')} amm={row.get('amm_mid_rlusd_per_xrp')} "
            f"spread={bps} bps {flag} ({row.get('status')})"
        )
    return "\n".join(lines)
