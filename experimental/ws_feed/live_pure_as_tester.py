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
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _runtime_for_disk(runtime: dict) -> dict:
    """Redact secrets before writing ws_as_demo_runtime.json."""
    out = dict(runtime)
    out["intel_ai_key"] = ""
    return out

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from experimental.ws_feed.engine_adapter_example import WSBookFeedAdapter, WS_AS_VERSION
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.pair_books import RlusdXrpPair
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
) -> None:
    """Sample WS state and run PureQuotePath (no profiles / no sacred gates)."""
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
            "ws_book_age_s": state.age_seconds(),
            "ws_message_count": state.message_count,
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
    )
    note = engine_dec["quote_decision_summary"]
    logger.info(note)

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
            "balance_xrp": xrp_bal,
            "balance_rlusd": rlusd_bal,
            "ws_book_age_s": state.age_seconds(),
            "ws_message_count": state.message_count,
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
            "quote_intents": [
                {"level": 1, "side": "bid", "price": engine_dec.get("suggested_bid"), "size_xrp": 1.0},
                {"level": 1, "side": "ask", "price": engine_dec.get("suggested_ask"), "size_xrp": 1.0},
            ] if engine_dec.get("would_quote") else [],
            "recent_decisions": runtime.get("recent_decisions", []) + [{
                "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
                "category": "as_pure",
                "message": note[:200],
            }][-20:],
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
    verbose: bool = False,
    serve_hud: bool = False,
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

    adapter = WSBookFeedAdapter(ws_feed, gamma=gamma, kappa=kappa)

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
    logger.info("This is simulation only. No orders placed. Pure A-S built-ins decide presence.")

    # Initial seed from WS snapshot (preferred for the WS version)
    try:
        await ws_feed.seed_from_ws_snapshot(limit=40)
    except Exception:
        logger.warning("WS seed failed, will rely on run()")

    # Runtime dict for GUI demo / compatibility (populated on each sample)
    gui_runtime: dict = {
        "as_mode": "pure",
        "ws_as_version": WS_AS_VERSION,
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
                snap = await comp_provider.fetch_snapshot()
                initial_comp = comp_provider.to_hud_state(snap)
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
        initial_hud = {
            "mid": gui_runtime.get("mid_price"),
            "best_bid": gui_runtime.get("best_bid_rlusd_per_xrp"),
            "best_ask": gui_runtime.get("best_ask_rlusd_per_xrp"),
            "book_spread_pct": gui_runtime.get("book_spread_pct"),
            "ws_age_s": gui_runtime.get("ws_book_age_s"),
            "ws_message_count": gui_runtime.get("ws_message_count"),
            "volatility_pct": gui_runtime.get("volatility_pct"),
            "as_reservation": gui_runtime.get("as_reservation"),
            "as_optimal_spread_pct": gui_runtime.get("as_optimal_spread_pct"),
            "as_gamma": gui_runtime.get("as_gamma"),
            "as_kappa": gui_runtime.get("as_kappa"),
            "suggested_bid": gui_runtime.get("suggested_bid"),
            "suggested_ask": gui_runtime.get("suggested_ask"),
            "would_quote": gui_runtime.get("market_edge_met"),
            "last_note": gui_runtime.get("quote_decision_summary", "Initial seed from WS snapshot - full samples starting..."),
            "as_mode": "pure",
            "balance_xrp": gui_runtime.get("balance_xrp"),
            "balance_rlusd": gui_runtime.get("balance_rlusd"),
            "inventory_label": gui_runtime.get("inventory_label"),
            "ws_as_version": gui_runtime.get("ws_as_version", WS_AS_VERSION),
            "zero_quote_reason": gui_runtime.get("zero_quote_reason"),
            "bot_address": config.bot_account_address or "r... (from config)",
            **{k: v for k, v in initial_comp.items() if k not in ("top_competitors",)},
            "top_competitors": initial_comp.get("top_competitors", []),
            **_hud_intel_fields(),
            "ai_edge_quality": gui_runtime.get("ai_edge_quality", 0.0),
            "ai_is_skimmable": gui_runtime.get("ai_is_skimmable", False),
            "ai_rationale": gui_runtime.get("ai_rationale", ""),
            "ai_suggested_posture": gui_runtime.get("ai_suggested_posture", "off"),
        }
        hud_update_state(initial_hud)

    if seconds > 0:
        end = time.monotonic() + seconds
    else:
        end = float("inf")  # unlimited run (until Ctrl+C); for long data collection like 11k+ cycles
    last_sample = 0.0
    last_json_save = 0.0

    try:
        while time.monotonic() < end:
            now = time.monotonic()
            if now - last_sample >= sample_interval:
                # Fetch competitor intel here in main loop (comp_provider in scope)
                comp_snapshot = {}
                if comp_provider:
                    try:
                        snap = await comp_provider.fetch_snapshot()
                        comp_snapshot = comp_provider.to_hud_state(snap)
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
                )
                last_sample = now

                # Optional: print compact GUI-ready snapshot for demo (copy-paste into Streamlit or save as json)
                if verbose:
                    compact = {k: gui_runtime.get(k) for k in ("market_edge_met", "quote_decision_summary", "as_reservation", "as_optimal_spread_pct", "ws_book_age_s", "ws_message_count")}
                    logger.info("[GUI DEMO RUNTIME] %s", compact)

                # Feed the new real-time A-S HUD (the dedicated "new gui" for WS + pure A-S)
                if hud_update_state:
                    hud_state = {
                        "mid": gui_runtime.get("mid_price"),
                        "best_bid": gui_runtime.get("best_bid_rlusd_per_xrp"),
                        "best_ask": gui_runtime.get("best_ask_rlusd_per_xrp"),
                        "book_spread_pct": gui_runtime.get("book_spread_pct"),
                        "ws_age_s": gui_runtime.get("ws_book_age_s"),
                        "ws_message_count": gui_runtime.get("ws_message_count"),
                        "volatility_pct": gui_runtime.get("volatility_pct"),
                        "as_reservation": gui_runtime.get("as_reservation"),
                        "as_optimal_spread_pct": gui_runtime.get("as_optimal_spread_pct"),
                        "as_gamma": gui_runtime.get("as_gamma"),
                        "as_kappa": gui_runtime.get("as_kappa"),
                        "suggested_bid": None,  # could compute if needed
                        "suggested_ask": None,
                        "would_quote": gui_runtime.get("market_edge_met"),
                        "last_note": gui_runtime.get("quote_decision_summary"),
                        "as_mode": "pure",
                        "balance_xrp": gui_runtime.get("balance_xrp"),
                        "balance_rlusd": gui_runtime.get("balance_rlusd"),
                        "inventory_label": gui_runtime.get("inventory_label"),
                        "ws_as_version": gui_runtime.get("ws_as_version", WS_AS_VERSION),
                        "zero_quote_reason": gui_runtime.get("zero_quote_reason"),
                        "bot_address": config.bot_account_address or "r... (set bot_account_address in config or use --xrp-bal etc for demo)",
                        # Full competitor intelligence (from persistent scraper)
                        # Feeds Intelligence tab + A-S (pressure adjusts effective vol for reservation math).
                        **{k: v for k, v in comp_snapshot.items() if k not in ("top_competitors",)},  # flat for HUD
                        "top_competitors": comp_snapshot.get("top_competitors", []),
                        "ai_edge_quality": gui_runtime.get("ai_edge_quality", 0.0),
                        "ai_is_skimmable": gui_runtime.get("ai_is_skimmable", False),
                        "ai_rationale": gui_runtime.get("ai_rationale", ""),
                        "ai_suggested_posture": gui_runtime.get("ai_suggested_posture", "off"),
                        # Intelligence API config (from Config tab) — for AI analysis of competitor ledger addresses / trending.
                        # AI is strictly advisory. It never mutates A-S reservation price or quoting decisions.
                        **_hud_intel_fields(),
                    }
                    hud_update_state(hud_state)

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
        try:
            await ws_task
        except Exception:
            pass

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
            verbose=args.verbose,
            serve_hud=args.serve_hud,
            intel_ai_provider=intel_provider,
            intel_ai_key=intel_key,
            intel_ai_model=intel_model,
        )
    )


if __name__ == "__main__":
    main()
