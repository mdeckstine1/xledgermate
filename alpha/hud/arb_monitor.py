"""Read-only CLOB vs AMM arb monitor for Alpha HUD (no trades, no engine coupling)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ARB_CACHE: Dict[str, Any] = {
    "updated_utc": None,
    "latest": None,
    "history": [],
    "summary": {},
}

_DEFAULT_DISLOCATION_BPS = 8.0


def _logs_dir(root: Optional[Path] = None) -> Path:
    return root if root is not None else Path("logs")


def _read_alpha_mid(logs_dir: Path) -> Optional[float]:
    path = logs_dir / "alpha_runtime_state.json"
    if not path.is_file():
        return None
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        mid = data.get("mid")
        if mid is not None and float(mid) > 0:
            return float(mid)
        book = data.get("book") or {}
        mid = book.get("mid")
        if mid is not None and float(mid) > 0:
            return float(mid)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _history_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "samples": 0,
            "dislocation_count": 0,
            "dislocation_pct": 0.0,
            "max_spread_bps": None,
            "avg_spread_bps": None,
        }
    bps_vals = [float(r["spread_bps"]) for r in rows if r.get("spread_bps") is not None]
    disloc = sum(1 for r in rows if r.get("dislocation"))
    return {
        "samples": len(rows),
        "dislocation_count": disloc,
        "dislocation_pct": round(disloc / len(rows) * 100.0, 1) if rows else 0.0,
        "max_spread_bps": round(max(bps_vals), 2) if bps_vals else None,
        "avg_spread_bps": round(sum(bps_vals) / len(bps_vals), 2) if bps_vals else None,
    }


def refresh_arb_snapshot(
    *,
    logs_dir: Optional[Path] = None,
    dislocation_bps: float = _DEFAULT_DISLOCATION_BPS,
    history_limit: int = 96,
) -> Dict[str, Any]:
    """
    Poll AMM vs CLOB mid and append JSONL (read-only).

    Uses Alpha runtime mid for CLOB reference — does not call the trading engine.
    """
    from config.settings import BotConfig
    from experimental.arb.clob_amm_monitor import (
        record_clob_amm_snapshot,
        tail_clob_amm_records,
    )

    logs = _logs_dir(logs_dir)
    cfg = BotConfig.load()
    clob_mid = _read_alpha_mid(logs)
    row = record_clob_amm_snapshot(
        clob_mid=clob_mid,
        rpc_url=cfg.resolved_rpc_url(),
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_currency=cfg.resolved_rlusd_currency_code(),
        dislocation_bps=dislocation_bps,
        path=logs / "clob_amm_spread.jsonl",
    )
    history = tail_clob_amm_records(limit=history_limit, path=logs / "clob_amm_spread.jsonl")
    summary = _history_summary(history)
    out = {
        "mode": "read_only",
        "updated_utc": datetime.now(tz=timezone.utc).isoformat(),
        "dislocation_threshold_bps": dislocation_bps,
        "latest": row,
        "history": history[-24:],
        "summary": summary,
        "note": (
            "Monitor only — no arb execution. Alpha engine unchanged. "
            "Future live arb needs wallet B + xledgermate-arb service."
        ),
    }
    global _ARB_CACHE
    _ARB_CACHE = out
    logger.info(
        "arb_monitor | clob=%s amm=%s spread_bps=%s disloc=%s",
        row.get("clob_mid_rlusd_per_xrp"),
        row.get("amm_mid_rlusd_per_xrp"),
        row.get("spread_bps"),
        row.get("dislocation"),
    )
    return out


def arb_snapshot_cached(
    *,
    logs_dir: Optional[Path] = None,
    history_limit: int = 96,
) -> Dict[str, Any]:
    """Return cache; backfill history from JSONL if cache empty."""
    from experimental.arb.clob_amm_monitor import tail_clob_amm_records

    if _ARB_CACHE.get("latest"):
        return dict(_ARB_CACHE)

    logs = _logs_dir(logs_dir)
    history = tail_clob_amm_records(limit=history_limit, path=logs / "clob_amm_spread.jsonl")
    latest = history[-1] if history else None
    return {
        "mode": "read_only",
        "updated_utc": None,
        "dislocation_threshold_bps": _DEFAULT_DISLOCATION_BPS,
        "latest": latest,
        "history": history[-24:],
        "summary": _history_summary(history),
        "note": "Waiting for first arb poll — open Arb tab or wait ~60s.",
    }
