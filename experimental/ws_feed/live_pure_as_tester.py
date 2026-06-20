#!/usr/bin/env python3
"""
Live tester for the COMMITTED WS + pure A-S future of xledgermate.

This exercises the real WsBookFeed (live WebSocket book subscriptions + state)
+ the exact provable long-run wiring (assess_inventory, build_quote_adjustments,
dynamic policy, etc.) + pure AvellanedaStrategy (A-S built-in protections only).

No hard gate. No legacy heuristic guards in the decision path.
No secondary/Anodos dependency in the core path (deprioritized — see handoff).

Purpose: See in real time, on the actual mainnet RLUSD/XRP book, what the
future production version would be outputting (policy strings, presence decision,
would-be quote levels via reservation + optimal spread).

This is read-only / simulation only. No orders are placed. Inventory is
assumed from recent run data for realism (you can override via args).

**IMPORTANT: Use the project virtual environment**
Activate first (PowerShell, from project root):
  .\\.venv\\Scripts\\Activate.ps1
  (or simply: .venv\\Scripts\\Activate.ps1)
Then run the tester. This keeps fastapi/uvicorn (for the real-time HUD) and
all other deps properly scoped.

Run:
  # Short demo run
  python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 300 --sample-interval 4 --verbose
  (Grok key: set XLG_GROK_KEY in .env once — see .env.example)
  # Long run (e.g. to collect 11k+ cycles like the gated VPS run; use --seconds 0 for unlimited)
  python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose --intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-3
  (The --serve-hud flag starts the new real-time HUD at http://127.0.0.1:8765)

We are committed. This (WS architecture + pure A-S + replicated wiring) is the path.
The sacred long-run hard-gate data is used only for validation/calibration.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _runtime_for_disk(runtime: dict) -> dict:
    """Redact secrets before writing ws_as_demo_runtime.json."""
    out = dict(runtime)
    out["intel_ai_key"] = ""
    return out


def _session_fields(runtime: dict) -> dict[str, Any]:
    """HUD / GUI session counters (sample count + presence %)."""
    history = runtime.get("sample_history") or []
    count = runtime.get("sample_count")
    if count is None:
        count = len(history)
    return {
        "sample_count": count,
        "as_presence_pct": runtime.get("as_presence_pct"),
        "presence_by_pressure": runtime.get("presence_by_pressure"),
        "zero_quote_breakdown": runtime.get("zero_quote_breakdown"),
        "soak_evaluation": runtime.get("soak_evaluation"),
        "open_offers_count": runtime.get("open_offers_count"),
        "last_execution_summary": runtime.get("last_execution_summary"),
        "fills_session": int(runtime.get("fills_session") or 0),
        "session_pnl_balance_xrp": runtime.get("session_pnl_balance_xrp"),
        "session_spread_capture_xrp": runtime.get("session_spread_capture_xrp"),
        "mean_markout_30s_pct": runtime.get("mean_markout_30s_pct"),
        "toxic_fill_ratio_30s": runtime.get("toxic_fill_ratio_30s"),
        "fill_quality_summary": runtime.get("fill_quality_summary"),
        "g2_size_mult": runtime.get("g2_size_mult"),
        "g2_spread_mult": runtime.get("g2_spread_mult"),
        "g2_grade": runtime.get("g2_grade"),
        "g2_active": runtime.get("g2_active"),
        "g2_summary": runtime.get("g2_summary"),
    }


def _wealth_fields(runtime: dict) -> dict[str, Any]:
    """RLUSD-stable wealth sidebar fields (enrichment is stripped unless passed through)."""
    try:
        from core.wealth_metrics import wealth_hud_payload

        return wealth_hud_payload(runtime)
    except Exception:
        return {}


def _ws_freshness_payload(ws_feed: WsBookFeed) -> dict[str, Any]:
    """Recompute age from live BookState (monotonic clock); push every ~1s to HUD."""
    snap = ws_feed.freshness_snapshot()
    return {
        "ws_age_s": snap["ws_book_age_s"],
        "ws_message_count": snap["ws_message_count"],
        "ws_book_last_update_unix": snap["ws_book_last_update_unix"],
        "ws_book_last_update_utc": snap["ws_book_last_update_utc"],
        **ws_feed.feed_health_snapshot(),
    }


def _portfolio_xrp_equiv(runtime: dict) -> Optional[float]:
    """Portfolio in XRP-equivalent for HUD (runtime field or balance+mid fallback)."""
    try:
        port = runtime.get("portfolio_value_xrp")
        if port is not None and float(port) > 0:
            return float(port)
    except (TypeError, ValueError):
        pass
    try:
        mid = float(runtime.get("mid_price") or runtime.get("mid") or 0)
        bx = float(runtime.get("balance_xrp") or 0)
        br = float(runtime.get("balance_rlusd") or 0)
    except (TypeError, ValueError):
        return None
    if mid > 0:
        return bx + br / mid
    return None


def _hud_market_payload(runtime: dict, **extra: Any) -> dict[str, Any]:
    """Shared Live-tab fields: ladder, sizes, A-S, balances."""
    from experimental.ws_feed.hud_intel_support import lane_ladder_hud_fields

    port = _portfolio_xrp_equiv(runtime)
    payload = {
        "mid": runtime.get("mid_price"),
        "mid_price": runtime.get("mid_price"),
        "best_bid": runtime.get("best_bid_rlusd_per_xrp"),
        "best_ask": runtime.get("best_ask_rlusd_per_xrp"),
        "best_bid_rlusd_per_xrp": runtime.get("best_bid_rlusd_per_xrp"),
        "best_ask_rlusd_per_xrp": runtime.get("best_ask_rlusd_per_xrp"),
        "book_spread_pct": runtime.get("book_spread_pct"),
        "book_bids": runtime.get("book_bids") or [],
        "book_asks": runtime.get("book_asks") or [],
        "ws_age_s": runtime.get("ws_book_age_s"),
        "ws_message_count": runtime.get("ws_message_count"),
        "ws_book_last_update_unix": runtime.get("ws_book_last_update_unix"),
        "ws_book_last_update_utc": runtime.get("ws_book_last_update_utc"),
        "volatility_pct": runtime.get("volatility_pct"),
        "as_reservation": runtime.get("as_reservation"),
        "inside_l1": runtime.get("inside_l1"),
        "reservation_to_bbo_delta_bps": runtime.get("reservation_to_bbo_delta_bps"),
        "effective_quote_age_at_fill_seconds": runtime.get(
            "effective_quote_age_at_fill_seconds"
        ),
        "recent_fill_quote_ages": runtime.get("recent_fill_quote_ages") or [],
        "as_optimal_spread_pct": runtime.get("as_optimal_spread_pct"),
        "as_gamma": runtime.get("as_gamma"),
        "as_kappa": runtime.get("as_kappa"),
        "suggested_bid": runtime.get("suggested_bid"),
        "suggested_ask": runtime.get("suggested_ask"),
        "would_quote": runtime.get("market_edge_met"),
        "last_note": runtime.get("quote_decision_summary"),
        "as_mode": "pure",
        "ws_as_version": extra.pop("ws_as_version", None) or current_ws_as_version(),
        "balance_xrp": runtime.get("balance_xrp"),
        "balance_rlusd": runtime.get("balance_rlusd"),
        "portfolio_value_xrp": port,
        "inventory_label": runtime.get("inventory_label"),
        "zero_quote_reason": runtime.get("zero_quote_reason"),
        "zero_quote_detail": runtime.get("zero_quote_detail"),
        "zero_quote_operator_note": runtime.get("zero_quote_operator_note"),
        "tight_book_note": runtime.get("tight_book_note"),
        "quote_intents": runtime.get("quote_intents") or [],
        "order_levels": runtime.get("order_levels", 3),
        "l1_xrp": runtime.get("l1_xrp"),
        "bid_size_xrp": runtime.get("bid_size_xrp"),
        "ask_size_xrp": runtime.get("ask_size_xrp"),
        "ai_edge_quality": runtime.get("ai_edge_quality", 0.0),
        "ai_is_skimmable": runtime.get("ai_is_skimmable", False),
        "ai_rationale": runtime.get("ai_rationale", ""),
        "ai_suggested_posture": runtime.get("ai_suggested_posture", "off"),
        "competitor_pressure": runtime.get("competitor_pressure"),
        "competitor_observed_spread_pct": runtime.get("competitor_observed_spread_pct"),
        "competitor_depth_xrp": runtime.get("competitor_depth_xrp"),
        "competitor_skim_advice": runtime.get("competitor_skim_advice"),
        "num_active_mms": runtime.get("num_active_mms"),
        "our_lane_xrp": runtime.get("our_lane_xrp"),
        "peer_lane_count": runtime.get("peer_lane_count"),
        "peer_pressure": runtime.get("peer_pressure"),
        "book_regime_pressure": runtime.get("book_regime_pressure"),
        "spread_regime_gap_bps": runtime.get("spread_regime_gap_bps"),
        "regime_channel_active": runtime.get("regime_channel_active"),
        "peer_lane_low_xrp": runtime.get("peer_lane_low_xrp"),
        "peer_lane_high_xrp": runtime.get("peer_lane_high_xrp"),
        "peer_fled_touch_count": runtime.get("peer_fled_touch_count"),
        "top_competitors": runtime.get("top_competitors") or [],
        "top_peers": runtime.get("top_peers") or [],
        "competitor_nicknames": runtime.get("competitor_nicknames") or {},
        "intel_ai_provider": runtime.get("intel_ai_provider"),
        "intel_ai_key": runtime.get("intel_ai_key", ""),
        "intel_ai_model": runtime.get("intel_ai_model"),
        "intel_ai_enabled": runtime.get("intel_ai_enabled", True),
        "performance_metrics": runtime.get("performance_metrics"),
        "g6_version": runtime.get("g6_version"),
        "g6_activation_tier": runtime.get("g6_activation_tier"),
        "g6_gate_pass": runtime.get("g6_gate_pass"),
        "g6_activation_summary": runtime.get("g6_activation_summary"),
        "g7_summary": runtime.get("g7_summary"),
        "g7_scaler_label": runtime.get("g7_scaler_label"),
        "worst_vs_touch_bps": runtime.get("worst_vs_touch_bps"),
        "quote_visibility_summary": runtime.get("quote_visibility_summary"),
        "bid_touch_backoff_bps": runtime.get("bid_touch_backoff_bps"),
        "ask_touch_backoff_bps": runtime.get("ask_touch_backoff_bps"),
        "g7_bid_role": runtime.get("g7_bid_role"),
        "g7_ask_role": runtime.get("g7_ask_role"),
        "g7_solo_acquisition": runtime.get("g7_solo_acquisition"),
        "g7_ask_sell_defense": runtime.get("g7_ask_sell_defense"),
        "peer_lane_empty": runtime.get("peer_lane_empty"),
        "solo_as_tighten": runtime.get("solo_as_tighten"),
        "buy_edge_gate_active": runtime.get("buy_edge_gate_active"),
        "buy_edge_gate_blocked": runtime.get("buy_edge_gate_blocked"),
        "buy_edge_implied_bps": runtime.get("buy_edge_implied_bps"),
        "buy_edge_gate_reason": runtime.get("buy_edge_gate_reason"),
        "acquire_ask_brake_active": runtime.get("acquire_ask_brake_active"),
        "acquire_ask_brake_blocked": runtime.get("acquire_ask_brake_blocked"),
        "acquire_ask_brake_reason": runtime.get("acquire_ask_brake_reason"),
        "g4_grade": runtime.get("g4_grade"),
        "g4_active": runtime.get("g4_active"),
        "g4_summary": runtime.get("g4_summary"),
        "g2_grade": runtime.get("g2_grade"),
        "g2_active": runtime.get("g2_active"),
        "g2_summary": runtime.get("g2_summary"),
        "g2_scaler_label": runtime.get("g2_scaler_label"),
        "fill_quality_summary": runtime.get("fill_quality_summary"),
        "execution_brakes_summary": runtime.get("execution_brakes_summary"),
        **_session_fields(runtime),
        **_wealth_fields(runtime),
        **extra,
    }
    payload.update(lane_ladder_hud_fields(runtime))
    try:
        from experimental.ws_feed.hud_intel_support import shadow_peer_lane_hud_fields

        payload.update(shadow_peer_lane_hud_fields(payload))
    except Exception:
        pass
    return payload

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from experimental.ws_feed.engine_adapter_example import WSBookFeedAdapter, WS_AS_VERSION
from experimental.ws_feed.pure_quote_path import current_ws_as_version
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.pure_dry_run_executor import PureDryRunExecutor
from experimental.ws_feed.ws_book_feed import WsBookFeed
from experimental.ws_runtime_analysis import append_runtime_sample
from utils.env_secrets import resolve_intel_ai_config
from utils.logging_setup import setup_logging

# Competitor scraping for aggressive analysis (experimental, pure A-S inputs only)
try:
    from experimental.market_analysis.competitor_intel import CompetitorIntelProvider, get_competitor_signals
except Exception:
    CompetitorIntelProvider = None
    get_competitor_signals = None

# AI analysis for competitive edge (revived from earlier discussion; augments A-S inputs with competitor-aware reasoning, no hard gates)
try:
    from experimental.ai_analysis.base import StubAIAnalyzer
    from experimental.ai_analysis.grok_analyzer import create_grok_analyzer_from_config
except Exception:
    StubAIAnalyzer = None

# New real-time HUD for WS + pure A-S (the "new gui" surface)
try:
    from experimental.ws_feed.real_time_as_hud import update_state as hud_update_state, run_hud, _current_state as _hud_current_state
except Exception:
    hud_update_state = None
    run_hud = None
    _hud_current_state = None

logger = logging.getLogger(__name__)


def _build_connector(config: BotConfig) -> XRPLConnector:
    return XRPLConnector(
        account_address=config.bot_account_address or "rLiveWsAsTesterXXXXXXXXXXXX",
        secret=None,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )



WS_STALE_REFRESH_S = 12.0
WS_FRESH_WAIT_S = 8.0


async def _wait_for_ws_feed(ws_feed: WsBookFeed, *, timeout_s: float = WS_FRESH_WAIT_S) -> None:
    """Wait for subscribe snapshots after background WS task starts."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if ws_feed.state.message_count >= 2 and ws_feed.age_seconds() < WS_STALE_REFRESH_S:
            return
        await asyncio.sleep(0.1)
    age = ws_feed.age_seconds()
    if age >= WS_STALE_REFRESH_S:
        logger.warning(
            "WS feed not fresh after %.0fs wait (age=%.1fs msgs=%s) — will retry refresh on samples",
            timeout_s,
            age,
            ws_feed.state.message_count,
        )


async def _fetch_comp_snapshot(
    comp_provider: Any,
    ws_feed: WsBookFeed,
    gui_runtime: dict,
    fallback_l1_xrp: float,
) -> dict:
    """On-chain scrape with posted-touch peer lane (G1) using WS book + prior L1."""
    from experimental.market_analysis.peer_lane import our_lane_from_runtime

    state = ws_feed.state
    bb, ba = state.best_prices()
    book = state.to_order_book() if hasattr(state, "to_order_book") else {"bids": [], "asks": []}
    our_lane = our_lane_from_runtime(
        l1_xrp=gui_runtime.get("l1_xrp"),
        bid_size_xrp=gui_runtime.get("bid_size_xrp"),
        ask_size_xrp=gui_runtime.get("ask_size_xrp"),
    )
    if our_lane <= 0:
        our_lane = fallback_l1_xrp
    snap = await comp_provider.fetch_snapshot(
        our_lane_xrp=our_lane,
        best_bid=bb,
        best_ask=ba,
        ws_bids=book.get("bids"),
        ws_asks=book.get("asks"),
    )
    return comp_provider.to_hud_state(snap)


async def _sample_and_decide(
    ws_feed: WsBookFeed,
    adapter: WSBookFeedAdapter,
    xrp_bal: float,
    rlusd_bal: float,
    target_ratio: float,
    verbose: bool = False,
    runtime: dict | None = None,
    comp_snapshot: dict | None = None,
    ai_analyzer=None,
    dry_run_executor: PureDryRunExecutor | None = None,
) -> None:
    """Sample WS state and run PureQuotePath (no profiles / no sacred gates)."""
    await ws_feed.refresh_if_stale(WS_STALE_REFRESH_S)
    state = ws_feed.state
    bb, ba = state.best_prices()
    mid = (bb + ba) / 2.0 if bb and ba else None
    spread = (ba - bb) / mid * 100.0 if mid else None

    if runtime is not None:
        runtime.update({
            "mid_price": mid,
            "best_bid_rlusd_per_xrp": bb,
            "best_ask_rlusd_per_xrp": ba,
            "book_spread_pct": spread,
            **state.freshness_snapshot(),
        })

    if not bb or not ba or bb <= 0 or ba <= 0 or not mid:
        return

    intel_enabled = runtime.get("intel_ai_enabled", True) if runtime else True
    book_for_ai = {
        "bids": state.to_order_book().get("bids", []) if hasattr(state, "to_order_book") else [],
        "asks": state.to_order_book().get("asks", []) if hasattr(state, "to_order_book") else [],
        "age_s": state.age_seconds(),
    }
    engine_dec = await adapter.compute_pure_as_decision(
        mid=mid,
        best_bid=bb,
        best_ask=ba,
        xrp_bal=xrp_bal,
        rlusd_bal=rlusd_bal,
        target_ratio=target_ratio,
        competitor_intel=comp_snapshot,
        ai_analyzer=ai_analyzer,
        intel_ai_enabled=intel_enabled,
        book_state_for_ai=book_for_ai,
        ws_book_age_s=state.age_seconds(),
    )
    note = engine_dec["quote_decision_summary"]
    logger.info(note)

    dry_diff = None
    if dry_run_executor is not None:
        dry_diff = dry_run_executor.sync(
            engine_dec.get("quote_intents") or [],
            would_quote=bool(engine_dec.get("would_quote")),
        )
        logger.info("[DRY-RUN] %s", dry_diff.summary)

    if verbose:
        logger.info(
            "[LIVE WS] age=%.1fs msgs=%s book_spread=%.3f%% bb=%.6f ba=%.6f | %s",
            state.age_seconds(),
            state.message_count,
            spread,
            bb,
            ba,
            engine_dec.get("zero_quote_detail", ""),
        )

    if runtime is not None:
        runtime.update({
            "mid_price": mid,
            "best_bid_rlusd_per_xrp": bb,
            "best_ask_rlusd_per_xrp": ba,
            "book_spread_pct": engine_dec.get("book_spread_pct", spread),
            "volatility_pct": engine_dec.get("volatility_pct"),
            "inventory_label": engine_dec.get("inventory_label"),
            "quote_decision_summary": note,
            "quoting_policy_label": engine_dec.get("quoting_policy_label"),
            "market_edge_met": engine_dec.get("would_quote"),
            "market_edge_pct": (engine_dec.get("as_optimal_spread_pct") or 0) / 2.0,
            "ws_as_version": engine_dec.get("ws_as_version", WS_AS_VERSION),
            "zero_quote_reason": engine_dec.get("zero_quote_reason"),
            "zero_quote_detail": engine_dec.get("zero_quote_detail"),
            "zero_quote_operator_note": engine_dec.get("zero_quote_operator_note", ""),
            "tight_book_note": engine_dec.get("tight_book_note", ""),
            "balance_xrp": xrp_bal,
            "balance_rlusd": rlusd_bal,
            **state.freshness_snapshot(),
            "as_mode": "pure",
            "as_reservation": engine_dec.get("as_reservation"),
            "as_optimal_spread_pct": engine_dec.get("as_optimal_spread_pct"),
            "as_gamma": engine_dec.get("as_gamma"),
            "as_kappa": engine_dec.get("as_kappa"),
            "as_protected": True,
            "pause_bids": False,
            "pause_asks": False,
            **(comp_snapshot or {}),
            "ai_edge_quality": engine_dec.get("ai_edge_quality", 0.0),
            "ai_is_skimmable": engine_dec.get("ai_is_skimmable", False),
            "ai_rationale": engine_dec.get("ai_rationale", ""),
            "ai_suggested_posture": engine_dec.get("ai_suggested_posture", "off"),
            "intel_ai_provider": runtime.get("intel_ai_provider", "stub"),
            "intel_ai_key": runtime.get("intel_ai_key", ""),
            "intel_ai_model": runtime.get("intel_ai_model", "grok-3"),
            "intel_ai_enabled": intel_enabled,
            "l1_xrp": engine_dec.get("l1_xrp"),
            "bid_size_xrp": engine_dec.get("bid_size"),
            "ask_size_xrp": engine_dec.get("ask_size"),
            "pure_as_size_rationale": engine_dec.get("pure_as_size_rationale", ""),
            "suggested_bid": engine_dec.get("suggested_bid"),
            "suggested_ask": engine_dec.get("suggested_ask"),
            "quote_intents": engine_dec.get("quote_intents") or [],
            "order_levels": runtime.get("order_levels", 3),
            "recent_decisions": runtime.get("recent_decisions", []) + [{
                "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
                "category": "as_pure",
                "message": note[:200],
            }][-20:],
            **ws_feed.feed_health_snapshot(),
        })
        if dry_diff is not None:
            runtime.update({
                "dry_run": True,
                "dry_run_execution": dry_diff.as_dict(),
                "last_execution_summary": dry_diff.summary,
                "open_offers_count": len(dry_diff.open_offers),
                "open_offers": dry_diff.open_offers,
                "offers_placed_last_cycle": len(dry_diff.to_place),
            })
        append_runtime_sample(
            runtime,
            {
                "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
                "mid": mid,
                "best_bid": bb,
                "best_ask": ba,
                "book_spread_pct": spread,
                "as_optimal_spread_pct": engine_dec.get("as_optimal_spread_pct"),
                "spread_gap_pct": spread - (engine_dec.get("as_optimal_spread_pct") or 0),
                "as_reservation": engine_dec.get("as_reservation"),
                "would_quote": engine_dec.get("would_quote"),
                "competitor_pressure": comp_snapshot.get("competitor_pressure") if comp_snapshot else None,
                "competitor_observed_spread_pct": comp_snapshot.get("competitor_observed_spread_pct") if comp_snapshot else None,
                "volatility_pct": engine_dec.get("volatility_pct"),
                "ws_book_age_s": state.age_seconds(),
                "inventory_label": engine_dec.get("inventory_label"),
                "zero_quote_reason": engine_dec.get("zero_quote_reason"),
                "inside_l1": engine_dec.get("inside_l1"),
                "reservation_to_bbo_delta_bps": engine_dec.get("reservation_to_bbo_delta_bps"),
            },
        )


async def run_live_test(
    *,
    seconds: float,
    gamma: float,
    kappa: float,
    xrp_bal: float,
    rlusd_bal: float,
    target_ratio: float,
    sample_interval: float = 8.0,
    ws_refresh_seconds: float = 20.0,
    verbose: bool = False,
    serve_hud: bool = False,
    dry_run_offers: bool = True,
    intel_ai_provider: str = "stub",
    intel_ai_key: str = "",
    intel_ai_model: str = "grok-3",
) -> None:
    config = BotConfig.load()
    connector = _build_connector(config)
    rpc = config.resolved_rpc_url()
    ws_url = rpc_url_to_websocket_url(rpc)
    taker = (config.bot_account_address or "").strip() or "rLiveWsAsTesterXXXXXXXXXXXX"

    pair = RlusdXrpPair(
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        taker=taker,
    )

    # On start, show recent demo runtimes so user knows previous data is safe (backups created on overwrite)
    demo_dir = Path("logs")
    if demo_dir.exists():
        demos = sorted(demo_dir.glob("ws_as_demo_runtime*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        if demos:
            logger.info("Recent WS demo runtimes (previous sessions backed up on tester restart):")
            for d in demos:
                logger.info("  %s", d)

    ws_feed = WsBookFeed(
        connector=connector,
        ws_url=ws_url,
        pair=pair,
        verbose=verbose,
    )

    # Persistent competitor intelligence scraper (aggressive on-chain for beating competitors)
    comp_provider = None
    if CompetitorIntelProvider:
        try:
            comp_provider = CompetitorIntelProvider(connector, pair)
            logger.info("CompetitorIntelProvider active — scraping other MMs for pure A-S signals. Intelligence tab in HUD shows profiles + skim advice.")
        except Exception:
            logger.warning("Could not init CompetitorIntelProvider")

    # Grok-integrated AI for per-sample (when configured). This is the main extension point for "grok integrated" on the WS branch.
    # Real Grok (via GrokAIAnalyzer) replaces the stub for per-sample edge/pressure analysis when a key is provided.
    # Advisory only — results appear in decision notes and Intelligence tab cards. The A-S math itself is untouched.
    ai_analyzer = None
    if intel_ai_provider == "grok" and intel_ai_key:
        ai_analyzer = create_grok_analyzer_from_config(intel_ai_key, intel_ai_model)
        if ai_analyzer:
            logger.info("REAL GROK integrated into per-sample loop (model=%s, via GrokAIAnalyzer). "
                        "Uses micro-structure prompt with current pressure + book state. "
                        "Note: real calls are expensive — the on-demand 'Analyze with AI' button in the HUD is still best for deep single-competitor dives.", intel_ai_model)
    if ai_analyzer is None and StubAIAnalyzer:
        ai_analyzer = StubAIAnalyzer()
        logger.info("AI analysis using enhanced stub (real Grok available when --intel-ai-provider=grok + key configured).")

    l1_config = float(config.order_sizes[0]) if config.order_sizes else 150.0
    order_sizes = tuple(float(x) for x in (config.order_sizes or [l1_config]))
    adapter = WSBookFeedAdapter(
        ws_feed,
        gamma=gamma,
        kappa=kappa,
        configured_l1_xrp=l1_config,
        min_order_size_xrp=float(config.min_order_size_xrp),
        balance_fraction_k=0.07,
        order_levels=int(config.order_levels),
        level_spread_increment=float(config.level_spread_increment),
        configured_order_sizes=order_sizes,
    )
    logger.info(
        "B2 dynamic sizing: L1=min(%.0f, 7%%×XRP bal) min_order=%.1f",
        l1_config,
        float(config.min_order_size_xrp),
    )

    duration_str = f"{seconds:.0f}s" if seconds > 0 else "unlimited (until Ctrl+C)"
    logger.info(
        "LIVE WS + PURE A-S v%s | WS=%s | gamma=%.2f kappa=%.2f | duration=%s | PureQuotePath (no profiles)",
        WS_AS_VERSION,
        ws_url,
        gamma,
        kappa,
        duration_str,
    )
    if serve_hud:
        logger.info("New real-time HUD (new GUI surface) will be served alongside the decisions.")
    logger.info(
        "Starting inventory assumption: XRP=%.1f RLUSD=%.1f target_ratio=%.2f (adjust with --xrp-bal etc.)",
        xrp_bal, rlusd_bal, target_ratio,
    )
    dry_run_executor = PureDryRunExecutor() if dry_run_offers else None
    if dry_run_offers:
        logger.info(
            "D2 dry-run offers ON — virtual place/cancel from PureQuotePath (no ledger txs)."
        )
    else:
        logger.info("Dry-run offers OFF — decision-only mode.")

    # Background WS subscribe loop — without this, book age grows forever after one-time seed.
    ws_task = asyncio.create_task(
        ws_feed.run_forever(http_refresh_seconds=ws_refresh_seconds),
        name="ws_book_feed",
    )
    await _wait_for_ws_feed(ws_feed)
    logger.info(
        "WS background feed active (age=%.1fs msgs=%s refresh=%.0fs)",
        ws_feed.age_seconds(),
        ws_feed.state.message_count,
        ws_refresh_seconds,
    )

    # Runtime dict for GUI demo / compatibility (populated on each sample)
    gui_runtime: dict = {
        "as_mode": "pure",
        "ws_as_version": WS_AS_VERSION,
        "order_levels": int(config.order_levels),
        "dry_run": True,
        "recent_decisions": [],
        # Intelligence API config (for AI competitor address trending — advisory only)
        "intel_ai_provider": intel_ai_provider,
        "intel_ai_key": "",  # never persist the real key in the demo runtime json (security)
        "intel_ai_model": intel_ai_model,
        "intel_ai_enabled": True,
    }

    # Merge any live config that was set via the HUD form (/set_intel_config) so form changes persist across samples
    if _hud_current_state and _hud_current_state.get("intel_ai_key"):
        gui_runtime["intel_ai_provider"] = _hud_current_state.get("intel_ai_provider", gui_runtime["intel_ai_provider"])
        gui_runtime["intel_ai_key"] = _hud_current_state.get("intel_ai_key", gui_runtime["intel_ai_key"])
        gui_runtime["intel_ai_model"] = _hud_current_state.get("intel_ai_model", gui_runtime["intel_ai_model"])
        gui_runtime["intel_ai_enabled"] = _hud_current_state.get("intel_ai_enabled", gui_runtime["intel_ai_enabled"])

    # Seed initial data *before* starting the HUD server so the very first poll after restart
    # gets rich data for Live + Intelligence tabs. This prevents blank pages on full stop/restart + hard refresh.
    try:
        initial_comp = {}
        if comp_provider:
            try:
                initial_comp = await _fetch_comp_snapshot(
                    comp_provider, ws_feed, gui_runtime, l1_config,
                )
            except Exception:
                initial_comp = {}
        await _sample_and_decide(
            ws_feed,
            adapter,
            xrp_bal,
            rlusd_bal,
            target_ratio,
            verbose=verbose,
            runtime=gui_runtime,
            comp_snapshot=initial_comp,
            ai_analyzer=ai_analyzer,
            dry_run_executor=dry_run_executor,
        )
        # Quick save
        out = Path("logs/ws_as_demo_runtime.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as f:
            json.dump(_runtime_for_disk(gui_runtime), f, default=str, indent=2)
        logger.info("Seeded initial data (including Live tab book/A-S fields, competitor intel, AI config) to HUD memory and logs/ws_as_demo_runtime.json")
    except Exception as e:
        logger.warning("Initial seed for HUD/json failed: %s", e)

    # Start the new real-time A-S HUD (the dedicated live GUI surface for WS + pure A-S)
    if serve_hud and run_hud:
        run_hud(host="127.0.0.1", port=8765, background=True)
        print("   → NEW GUI: Open http://127.0.0.1:8765 in your browser for the dedicated real-time WS + pure A-S HUD")
        print("      (live book + A-S reservation, suggested levels, freshness, recent decisions — updates ~every 800ms)")

    def _hud_intel_fields() -> dict[str, Any]:
        key = intel_ai_key or ""
        prov = intel_ai_provider
        model = intel_ai_model
        enabled = True
        if _hud_current_state:
            key = _hud_current_state.get("intel_ai_key") or key
            prov = _hud_current_state.get("intel_ai_provider") or prov
            model = _hud_current_state.get("intel_ai_model") or model
            enabled = _hud_current_state.get("intel_ai_enabled", enabled)
        return {
            "intel_ai_provider": prov,
            "intel_ai_key": key,
            "intel_ai_model": model,
            "intel_ai_enabled": enabled,
        }

    if intel_ai_key and hud_update_state:
        hud_update_state(_hud_intel_fields())

    # Now send the rich initial state (built from the gui_runtime the seed just populated)
    # so the first browser poll gets full Live page data immediately.
    if hud_update_state:
        hud_update_state(
            _hud_market_payload(
                gui_runtime,
                last_note=gui_runtime.get(
                    "quote_decision_summary",
                    "Initial seed from WS snapshot - full samples starting...",
                ),
                bot_address=config.bot_account_address or "r... (from config)",
                **{k: v for k, v in initial_comp.items() if k not in ("top_competitors",)},
                top_competitors=initial_comp.get("top_competitors", []),
                **_hud_intel_fields(),
            )
        )

    if seconds > 0:
        end = time.monotonic() + seconds
    else:
        end = float("inf")  # unlimited run (until Ctrl+C); for long data collection like 11k+ cycles
    last_sample = 0.0
    last_json_save = 0.0
    last_hud_fresh = 0.0

    try:
        while time.monotonic() < end:
            now = time.monotonic()
            if hud_update_state and now - last_hud_fresh >= 1.0:
                hud_update_state(_ws_freshness_payload(ws_feed))
                last_hud_fresh = now
            if now - last_sample >= sample_interval:
                # Fetch competitor intel here in main loop (comp_provider in scope)
                comp_snapshot = {}
                if comp_provider:
                    try:
                        comp_snapshot = await _fetch_comp_snapshot(
                            comp_provider, ws_feed, gui_runtime, l1_config,
                        )
                    except Exception:
                        comp_snapshot = {}

                # Re-merge any live intel config set via HUD form /set_intel_config (Config tab Apply).
                # This ensures gui_runtime carries the key set mid-run, so the hud_state push below
                # does not clobber the server _current_state with a stale gui_runtime value (the root cause
                # of "key held on Apply then switched off on next poll").
                if _hud_current_state and _hud_current_state.get("intel_ai_key"):
                    gui_runtime["intel_ai_provider"] = _hud_current_state.get("intel_ai_provider", gui_runtime.get("intel_ai_provider", "stub"))
                    gui_runtime["intel_ai_key"] = _hud_current_state.get("intel_ai_key", gui_runtime.get("intel_ai_key", ""))
                    gui_runtime["intel_ai_model"] = _hud_current_state.get("intel_ai_model", gui_runtime.get("intel_ai_model", "grok-3"))
                    gui_runtime["intel_ai_enabled"] = _hud_current_state.get("intel_ai_enabled", gui_runtime.get("intel_ai_enabled", True))

                await _sample_and_decide(
                    ws_feed,
                    adapter,
                    xrp_bal,
                    rlusd_bal,
                    target_ratio,
                    verbose=verbose,
                    runtime=gui_runtime,
                    comp_snapshot=comp_snapshot,
                    ai_analyzer=ai_analyzer,
                    dry_run_executor=dry_run_executor,
                )
                last_sample = now

                # Optional: print compact GUI-ready snapshot for demo (copy-paste into Streamlit or save as json)
                if verbose:
                    compact = {k: gui_runtime.get(k) for k in ("market_edge_met", "quote_decision_summary", "as_reservation", "as_optimal_spread_pct", "ws_book_age_s", "ws_message_count")}
                    logger.info("[GUI DEMO RUNTIME] %s", compact)

                # Feed the new real-time A-S HUD (the dedicated "new gui" for WS + pure A-S)
                if hud_update_state:
                    hud_update_state(
                        _hud_market_payload(
                            gui_runtime,
                            bot_address=config.bot_account_address
                            or "r... (set bot_account_address in config or use --xrp-bal etc for demo)",
                            **{k: v for k, v in comp_snapshot.items() if k not in ("top_competitors",)},
                            top_competitors=comp_snapshot.get("top_competitors", []),
                            **_hud_intel_fields(),
                        )
                    )

                # Save the runtime JSON frequently while the tester is running
                # so you can load the *current* WS + pure A-S data into the main Streamlit GUI
                # (without waiting for the run to finish). This prevents "lost data".
                # Previous runs are automatically backed up as ws_as_demo_runtime_YYYYMMDD_HHMMSS.json
                # (including full Intelligence tab competitor profiles, pressure, skim advice, etc.).
                # The plain ws_as_demo_runtime.json is always the latest from the current tester session.
                # Long-run data stays in logs/runtime_state.json or your vps_ files.
                if now - last_json_save >= 5.0:
                    try:
                        out = Path("logs/ws_as_demo_runtime.json")
                        out.parent.mkdir(parents=True, exist_ok=True)
                        if out.exists():
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            backup = out.with_name(f"ws_as_demo_runtime_{ts}.json")
                            out.rename(backup)
                            logger.info("Backed up previous demo runtime to %s (prevents data loss on restart)", backup)
                        with out.open("w") as f:
                            json.dump(_runtime_for_disk(gui_runtime), f, default=str, indent=2)
                        logger.info("Updated logs/ws_as_demo_runtime.json with current WS data — load this in main Streamlit to see full GUI (sidebar, tickers, A-S sections, Intelligence tab) with live tester data.")
                    except Exception as e:
                        logger.warning("Could not update demo runtime JSON: %s", e)
                    last_json_save = now

            await asyncio.sleep(0.5)
    finally:
        ws_feed._stop.set()
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("WS task shutdown", exc_info=True)

    logger.info("Live WS + pure A-S test complete.")
    logger.info("GUI demo runtime available in-memory (last state has A-S fields, full competitor intel for Intelligence tab + standard decision_summary for Streamlit/ticker reuse).")

    # Save last gui_runtime for easy loading into the base Streamlit GUI or ticker for side-by-side demo
    try:
        out = Path("logs/ws_as_demo_runtime.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = out.with_name(f"ws_as_demo_runtime_{ts}.json")
            out.rename(backup)
            logger.info("Backed up previous demo runtime to %s", backup)
        with out.open("w") as f:
            json.dump(_runtime_for_disk(gui_runtime), f, default=str, indent=2)
        logger.info("Saved GUI demo runtime to %s — load this into streamlit_gui or inspect to see the WS + pure A-S decisions (including Intelligence tab with live competitor profiles, pressure, and skim advice). Previous runs are timestamped backups in the same folder.", out)
    except Exception as e:
        logger.warning("Could not save demo runtime: %s", e)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Live WS + pure A-S tester (committed future path)")
    parser.add_argument("--seconds", type=float, default=0.0, help="How long to run the live test in seconds (0 or negative = run forever until Ctrl+C; useful for long data collection like 11k+ cycles). We removed the short default so you can let it cook.")
    parser.add_argument("--gamma", type=float, default=0.35, help="A-S gamma (inventory risk aversion) - lower for more presence")
    parser.add_argument("--kappa", type=float, default=3.5, help="A-S kappa (arrival intensity) - higher for tighter/more competitive spreads")
    parser.add_argument("--xrp-bal", type=float, default=138.0, help="Assumed XRP balance for inventory calc")
    parser.add_argument("--rlusd-bal", type=float, default=124.0, help="Assumed RLUSD balance for inventory calc")
    parser.add_argument("--target-ratio", type=float, default=0.55, help="Target XRP ratio")
    parser.add_argument("--sample-interval", type=float, default=8.0, help="Seconds between decision samples")
    parser.add_argument(
        "--ws-refresh-seconds",
        type=float,
        default=20.0,
        help="Periodic WS snapshot reconciliation interval (default 20s)",
    )
    parser.add_argument(
        "--dry-run-offers",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="D2: sync virtual place/cancel from quote_intents (default on; no ledger txs)",
    )
    parser.add_argument("--verbose", action="store_true", help="Extra WS age / message count logging")
    parser.add_argument("--serve-hud", action="store_true", help="Start the new dedicated real-time WS + pure A-S HUD (http://127.0.0.1:8765) — this is the live 'new gui' surface for the committed path (book + A-S math + WS freshness updating in real time)")
    parser.add_argument(
        "--intel-ai-provider",
        default="stub",
        help="AI provider (stub, grok, ...). Defaults to grok when XLG_GROK_KEY is in .env",
    )
    parser.add_argument(
        "--intel-ai-key",
        default="",
        help="API key override. Otherwise XLG_GROK_KEY from .env / environment",
    )
    parser.add_argument(
        "--intel-ai-model",
        default="grok-3",
        help="Model name (or XLG_GROK_MODEL in .env)",
    )
    args = parser.parse_args()

    intel_provider, intel_key, intel_model = resolve_intel_ai_config(
        provider=args.intel_ai_provider,
        api_key=args.intel_ai_key,
        model=args.intel_ai_model,
    )
    if intel_key:
        logging.getLogger(__name__).info(
            "Intel AI: provider=%s model=%s (key loaded from .env/env, length=%d)",
            intel_provider,
            intel_model,
            len(intel_key),
        )

    asyncio.run(
        run_live_test(
            seconds=args.seconds,
            gamma=args.gamma,
            kappa=args.kappa,
            xrp_bal=args.xrp_bal,
            rlusd_bal=args.rlusd_bal,
            target_ratio=args.target_ratio,
            sample_interval=args.sample_interval,
            ws_refresh_seconds=args.ws_refresh_seconds,
            verbose=args.verbose,
            serve_hud=args.serve_hud,
            dry_run_offers=args.dry_run_offers,
            intel_ai_provider=intel_provider,
            intel_ai_key=intel_key,
            intel_ai_model=intel_model,
        )
    )


if __name__ == "__main__":
    main()
