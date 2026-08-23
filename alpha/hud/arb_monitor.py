"""Read-only CLOB vs AMM arb monitor for Alpha HUD (no trades, no engine coupling)."""

from __future__ import annotations

import json
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
    "cost_model": {},
    "universe": None,
    "fill_simulation": {},
}

_DEFAULT_DISLOCATION_BPS = 8.0
_DEFAULT_HISTORY_LIMIT = 288


def _logs_dir(root: Optional[Path] = None) -> Path:
    return root if root is not None else Path("logs")


def _read_alpha_book_context(logs_dir: Path) -> Dict[str, Any]:
    path = logs_dir / "alpha_runtime_state.json"
    out: Dict[str, Any] = {"mid": None, "spread_pct": None}
    if not path.is_file():
        return out
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        mid = data.get("mid")
        if mid is not None and float(mid) > 0:
            out["mid"] = float(mid)
        book = data.get("book") or {}
        if out["mid"] is None:
            mid = book.get("mid")
            if mid is not None and float(mid) > 0:
                out["mid"] = float(mid)
        spread_pct = book.get("spread_pct")
        if spread_pct is not None:
            out["spread_pct"] = float(spread_pct)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return out
    return out


def _enrich_history(
    rows: List[Dict[str, Any]],
    *,
    default_clob_spread_pct: Optional[float],
) -> List[Dict[str, Any]]:
    from experimental.arb.clob_amm_monitor import augment_clob_amm_row

    return [
        augment_clob_amm_row(r, default_clob_spread_pct=default_clob_spread_pct)
        for r in rows
    ]


def _cost_model_payload(spread_pct: Optional[float]) -> Dict[str, Any]:
    from experimental.arb.clob_amm_monitor import (
        DEFAULT_AMM_FEE_FALLBACK_BPS,
        DEFAULT_SLIPPAGE_BUFFER_BPS,
        estimate_arb_costs_bps,
    )

    costs = estimate_arb_costs_bps(clob_spread_pct=spread_pct)
    return {
        **costs,
        "formula": "net_edge = gross_spread − clob_half − amm_fee − slippage_buffer",
        "amm_fee_note": f"from pool TradingFee when polled; fallback {DEFAULT_AMM_FEE_FALLBACK_BPS:.0f} bps",
        "slippage_buffer_bps_default": DEFAULT_SLIPPAGE_BUFFER_BPS,
        "clob_spread_pct": spread_pct,
    }


def _read_alpha_balances(logs_dir: Path) -> Dict[str, float]:
    path = logs_dir / "alpha_runtime_state.json"
    out = {"xrp": 0.0, "rlusd": 0.0}
    if not path.is_file():
        return out
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        out["xrp"] = float(data.get("xrp") or data.get("balance_xrp") or 0)
        out["rlusd"] = float(data.get("rlusd") or data.get("balance_rlusd") or 0)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return out
    return out


def refresh_arb_snapshot(
    *,
    logs_dir: Optional[Path] = None,
    dislocation_bps: float = _DEFAULT_DISLOCATION_BPS,
    history_limit: int = _DEFAULT_HISTORY_LIMIT,
) -> Dict[str, Any]:
    """
    Poll AMM vs CLOB mid and append JSONL (read-only).

    Uses Alpha runtime mid for CLOB reference — does not call the trading engine.
    Adds paper discovery scoring (fill ladder, dwell, actionable, burst hint).
    """
    from config.settings import BotConfig
    from experimental.arb.arb_universe import refresh_arb_universe
    from experimental.arb.clob_amm_monitor import (
        record_clob_amm_snapshot,
        summarize_clob_amm_rows,
        tail_clob_amm_records,
    )
    from experimental.arb.discovery import (
        DISCOVERY_STATE_PATH,
        attach_discovery_to_universe,
        build_discovery_score,
    )
    from experimental.arb.fill_simulator import build_arb_fill_simulation_payload

    logs = _logs_dir(logs_dir)
    cfg = BotConfig.load()
    book_ctx = _read_alpha_book_context(logs)
    clob_mid = book_ctx.get("mid")
    spread_pct = book_ctx.get("spread_pct")
    row = record_clob_amm_snapshot(
        clob_mid=clob_mid,
        clob_spread_pct=spread_pct,
        rpc_url=cfg.resolved_rpc_url(),
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_currency=cfg.resolved_rlusd_currency_code(),
        dislocation_bps=dislocation_bps,
        path=logs / "clob_amm_spread.jsonl",
    )
    universe = refresh_arb_universe(
        rpc_url=cfg.resolved_rpc_url(),
        rlusd_currency=cfg.resolved_rlusd_currency_code(),
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_clob_mid=clob_mid,
        rlusd_spread_pct=spread_pct,
        dislocation_bps=dislocation_bps,
        path=logs / "arb_universe.jsonl",
    )
    bals = _read_alpha_balances(logs)
    discovery = build_discovery_score(
        row,
        xrp=bals["xrp"],
        rlusd=bals["rlusd"],
        state_path=logs / DISCOVERY_STATE_PATH.name,
    )
    # Persist discovery summary on the primary soak row path is already written;
    # re-append is heavy — keep discovery in cache + universe only.
    universe = attach_discovery_to_universe(universe, discovery)
    # Append lightweight discovery line for soak analysis
    try:
        disc_path = logs / "arb_discovery.jsonl"
        disc_path.parent.mkdir(parents=True, exist_ok=True)
        with disc_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "kind": "arb_discovery",
                        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
                        "mid_net_bps": discovery.get("mid_net_bps"),
                        "fill_profit_bps_250": discovery.get("fill_profit_bps_250"),
                        "fill_profit_bps_500": discovery.get("fill_profit_bps_500"),
                        "fill_profit_bps_1000": discovery.get("fill_profit_bps_1000"),
                        "maker_opt_bps_500": discovery.get("maker_opt_bps_500"),
                        "flag": discovery.get("flag"),
                        "actionable": discovery.get("actionable"),
                        "dwell": discovery.get("dwell"),
                        "burst": discovery.get("burst_recommended"),
                    },
                    separators=(",", ":"),
                    default=str,
                )
                + "\n"
            )
    except OSError as exc:
        logger.debug("arb_discovery log failed: %s", exc)

    history = tail_clob_amm_records(limit=history_limit, path=logs / "clob_amm_spread.jsonl")
    enriched = _enrich_history(history, default_clob_spread_pct=spread_pct)
    summary = summarize_clob_amm_rows(enriched, default_clob_spread_pct=spread_pct)
    cost_model = _cost_model_payload(spread_pct)
    fill_simulation = build_arb_fill_simulation_payload(latest=row, logs_dir=logs)
    out = {
        "mode": "read_only_discovery",
        "updated_utc": datetime.now(tz=timezone.utc).isoformat(),
        "dislocation_threshold_bps": dislocation_bps,
        "latest": row,
        "history": enriched[-24:],
        "summary": summary,
        "cost_model": cost_model,
        "universe": universe,
        "fill_simulation": fill_simulation,
        "discovery": discovery,
        "poll_sleep_seconds": int(discovery.get("poll_sleep_seconds") or 60),
        "note": (
            "Paper discovery — no arb execution. Primary KPI = fill@500 bps + dwell; "
            "mid net is secondary. ACTIONABLE = fill@500≥+3bps for 2+ polls & fundable."
        ),
    }
    global _ARB_CACHE
    _ARB_CACHE = out
    logger.info(
        "arb_monitor | clob=%s amm=%s mid_net=%s fill500=%s flag=%s actionable=%s burst=%s",
        row.get("clob_mid_rlusd_per_xrp"),
        row.get("amm_mid_rlusd_per_xrp"),
        discovery.get("mid_net_bps"),
        discovery.get("fill_profit_bps_500"),
        discovery.get("flag"),
        discovery.get("actionable"),
        discovery.get("burst_recommended"),
    )
    return out


def arb_snapshot_cached(
    *,
    logs_dir: Optional[Path] = None,
    history_limit: int = _DEFAULT_HISTORY_LIMIT,
) -> Dict[str, Any]:
    """Return cache; backfill history from JSONL if cache empty."""
    from experimental.arb.arb_universe import tail_universe_records
    from experimental.arb.clob_amm_monitor import summarize_clob_amm_rows, tail_clob_amm_records

    if _ARB_CACHE.get("latest"):
        return dict(_ARB_CACHE)

    logs = _logs_dir(logs_dir)
    book_ctx = _read_alpha_book_context(logs)
    spread_pct = book_ctx.get("spread_pct")
    history = tail_clob_amm_records(limit=history_limit, path=logs / "clob_amm_spread.jsonl")
    enriched = _enrich_history(history, default_clob_spread_pct=spread_pct)
    latest = enriched[-1] if enriched else None
    uni_rows = tail_universe_records(limit=1, path=logs / "arb_universe.jsonl")
    from experimental.arb.fill_simulator import build_arb_fill_simulation_payload

    fill_simulation = build_arb_fill_simulation_payload(latest=latest, logs_dir=logs)
    bals = _read_alpha_balances(logs)
    from experimental.arb.discovery import DISCOVERY_STATE_PATH, build_discovery_score

    discovery = build_discovery_score(
        latest,
        xrp=bals["xrp"],
        rlusd=bals["rlusd"],
        state_path=logs / DISCOVERY_STATE_PATH.name,
        update_dwell=False,
    )
    uni = uni_rows[-1] if uni_rows else None
    if uni:
        from experimental.arb.discovery import attach_discovery_to_universe

        uni = attach_discovery_to_universe(uni, discovery)
    return {
        "mode": "read_only_discovery",
        "updated_utc": None,
        "dislocation_threshold_bps": _DEFAULT_DISLOCATION_BPS,
        "latest": latest,
        "history": enriched[-24:],
        "summary": summarize_clob_amm_rows(enriched, default_clob_spread_pct=spread_pct),
        "cost_model": _cost_model_payload(spread_pct),
        "universe": uni,
        "fill_simulation": fill_simulation,
        "discovery": discovery,
        "poll_sleep_seconds": int(discovery.get("poll_sleep_seconds") or 60),
        "note": "Waiting for first arb poll — open Arb tab or wait ~60s (burst ~12s when hot).",
    }


def arb_soak_report_text(*, logs_dir: Optional[Path] = None, limit: int = _DEFAULT_HISTORY_LIMIT) -> str:
    from experimental.arb.arb_universe import format_universe_report
    from experimental.arb.clob_amm_monitor import format_clob_amm_report

    logs = _logs_dir(logs_dir)
    spread_pct = _read_alpha_book_context(logs).get("spread_pct")
    primary = format_clob_amm_report(
        logs_dir=logs,
        limit=limit,
        default_clob_spread_pct=spread_pct,
    )
    universe = format_universe_report(logs_dir=logs, limit=limit)
    return primary + "\n\n" + universe
