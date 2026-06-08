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
  .\.venv\Scripts\Activate.ps1
Then run the tester. This keeps fastapi/uvicorn (for the real-time HUD) and
all other deps properly scoped.

Run:
  python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 120 --verbose
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

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from core.perception import get_profile
from core.profile_edge import profile_min_edge_pct
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.ws_book_feed import WsBookFeed
from strategy.avellaneda_strategy import AvellanedaStrategy
from strategy.quote_decision import assess_inventory, build_quote_adjustments
from utils.logging_setup import setup_logging

# New real-time HUD for WS + pure A-S (the "new gui" surface)
try:
    from experimental.ws_feed.real_time_as_hud import update_state as hud_update_state, run_hud
except Exception:
    hud_update_state = None
    run_hud = None

logger = logging.getLogger(__name__)


def _build_connector(config: BotConfig) -> XRPLConnector:
    return XRPLConnector(
        account_address=config.bot_account_address or "rLiveWsAsTesterXXXXXXXXXXXX",
        secret=None,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )


def _make_minimal_assessment(book_spread_pct: float):
    """Minimal MarketAssessment so build_quote_adjustments / dynamic policy run cleanly for logging."""
    from core.market_conditions import (
        CONDITION_FAVORABLE,
        CONDITION_NEUTRAL,
        CONDITION_DEFENSIVE,
        CONDITION_HOSTILE,
        MarketAssessment,
    )

    if book_spread_pct < 0.10:
        cond = CONDITION_FAVORABLE
        health = 75
        label = "favorable"
    elif book_spread_pct > 0.25:
        cond = CONDITION_HOSTILE
        health = 25
        label = "hostile"
    elif book_spread_pct > 0.18:
        cond = CONDITION_DEFENSIVE
        health = 42
        label = "defensive"
    else:
        cond = CONDITION_NEUTRAL
        health = 60
        label = "neutral"

    spread_status = "tight" if book_spread_pct <= 0.12 else ("normal" if book_spread_pct < 0.22 else "wide")

    return MarketAssessment(
        condition=cond,
        condition_label=label,
        volatility_pct=0.0,
        volatility_level="low",
        liquidity_score=0.78,
        liquidity_level="high" if book_spread_pct < 0.15 else "moderate",
        book_spread_pct=book_spread_pct,
        book_spread_status=spread_status,
        health_score=health,
        recommended_profile="tight_spread",
        recommendation_reason=f"{label} live book",
        summary=f"{label} (health {health}) spread {book_spread_pct:.3f}%",
    )


async def _sample_and_decide(
    ws_feed: WsBookFeed,
    as_strat: AvellanedaStrategy,
    profile_name: str,
    xrp_bal: float,
    rlusd_bal: float,
    target_ratio: float,
    verbose: bool = False,
    runtime: dict | None = None,
) -> None:
    """Sample current WS state and run the pure A-S + replicated wiring decision.

    Also populates a runtime dict (base fields + A-S specific) so the output
    is directly usable to feed the existing Streamlit GUI or ticker for demo
    (load as runtime_state.json or pass to _render_* functions).
    """
    state = ws_feed.state
    bb, ba = state.best_prices()
    if not bb or not ba or bb <= 0 or ba <= 0:
        return

    mid = (bb + ba) / 2.0
    spread = (ba - bb) / mid * 100.0

    profile = get_profile(profile_name)
    min_edge = profile_min_edge_pct(profile)

    # Inventory assessment (exact same function as long-run)
    inv_state = assess_inventory(
        xrp_balance=xrp_bal,
        rlusd_balance=rlusd_bal,
        mid_price=mid,
        target_xrp_ratio=target_ratio,
        skew_strength=getattr(profile, "inventory_skew_strength", 1.0),
    )

    inv_skew = 0.0
    if "xrp_heavy" in inv_state.label:
        inv_skew = 0.30 if "slight" not in inv_state.label else 0.08
    elif "rlusd_heavy" in inv_state.label:
        inv_skew = -0.30 if "slight" not in inv_state.label else -0.08

    # Run the full build_quote_adjustments for the rich context strings
    # (inventory, momentum stub=0 for live simple test, book pressure, policy, etc.)
    # Use a minimal assessment so the dynamic policy path runs (we care about the strings).
    assessment = _make_minimal_assessment(spread)
    adj = build_quote_adjustments(
        profile=profile,
        assessment=assessment,
        inventory=inv_state,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=spread / 2.0,
        book_spread_pct=spread,
        depth_imbalance=0.0,
        min_edge_pct=min_edge,
        fill_quality=None,
        xrpl_fee_bps=2.0,
        fund_with_xrp_only=False,
        rlusd_balance=rlusd_bal,
        min_order_xrp=0.1,
        target_xrp_ratio=target_ratio,
        inventory_max_deviation=0.12,
        inventory_mode="market_make",
        toxic_off_touch_latched=False,
    )

    # Pure A-S using WS-fresh book
    as_quote = as_strat.compute_avellaneda_quote(
        mid_price=mid,
        inventory_skew=inv_skew,
        volatility_pct=0.0,
        best_bid=bb,
        best_ask=ba,
        book_spread_pct=spread,
        profile=profile,
    )

    # Pure decision: A-S built-in (reservation inside the book = safe to quote per math)
    as_met = (as_quote.reservation_price > bb and as_quote.reservation_price < ba)

    gen_n = 2 if as_met else 0
    note = (
        f"Generated {gen_n} quotes (two-sided) from mid={mid:.6f} RLUSD/XRP "
        f"| inventory={inv_state.label} "
        f"| {adj.decision_summary} "
        f"| PURE A-S: reservation={as_quote.reservation_price:.6f} "
        f"spread={as_quote.optimal_spread_pct:.3f}% "
        f"(gamma={as_strat.gamma}, kappa={as_strat.kappa})"
    )

    if as_met:
        note += f" | would quote bid~{as_quote.bid_price:.6f} ask~{as_quote.ask_price:.6f}"

    logger.info(note)

    if verbose:
        logger.info(
            "[LIVE WS] age=%.1fs msgs=%s book_spread=%.3f%% bb=%.6f ba=%.6f",
            state.age_seconds(),
            state.message_count,
            spread,
            bb,
            ba,
        )

    # --- Build runtime for GUI demo / compatibility ---
    if runtime is not None:
        runtime.update({
            "mid_price": mid,
            "best_bid_rlusd_per_xrp": bb,
            "best_ask_rlusd_per_xrp": ba,
            "book_spread_pct": spread,
            "inventory_label": inv_state.label,
            "quote_decision_summary": note,
            "quoting_policy_label": "PURE A-S (built-in protection)" if as_met else "PURE A-S (protected by math)",
            "market_edge_met": as_met,  # compatibility: A-S met acts as the edge flag
            "market_edge_pct": as_quote.optimal_spread_pct / 2.0,
            "active_profile": profile_name,
            "balance_xrp": xrp_bal,
            "balance_rlusd": rlusd_bal,
            "ws_book_age_s": state.age_seconds(),
            "ws_message_count": state.message_count,
            "as_mode": "pure",
            "as_reservation": as_quote.reservation_price,
            "as_optimal_spread_pct": as_quote.optimal_spread_pct,
            "as_gamma": as_strat.gamma,
            "as_kappa": as_strat.kappa,
            "as_protected": True,
            "as_presence_pct": None,  # caller can track session-wide
            "pause_bids": adj.pause_bids,
            "pause_asks": adj.pause_asks,
            "fill_quality_score": adj.fill_quality_score,
            # Synthesize a simple quote intent for the ladder (demo)
            "quote_intents": [
                {"level": 1, "side": "bid", "price": as_quote.bid_price, "size_xrp": as_quote.bid_size},
                {"level": 1, "side": "ask", "price": as_quote.ask_price, "size_xrp": as_quote.ask_size},
            ] if gen_n > 0 else [],
            # Add a recent decision event in base format for the table
            "recent_decisions": runtime.get("recent_decisions", []) + [{
                "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
                "category": "as_pure",
                "message": note[:200],
            }][-20:],  # keep last 20
        })


async def run_live_test(
    *,
    seconds: float,
    gamma: float,
    kappa: float,
    profile: str,
    xrp_bal: float,
    rlusd_bal: float,
    target_ratio: float,
    sample_interval: float = 8.0,
    verbose: bool = False,
    serve_hud: bool = False,
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

    ws_feed = WsBookFeed(
        connector=connector,
        ws_url=ws_url,
        pair=pair,
        verbose=verbose,
    )

    as_strat = AvellanedaStrategy(None, gamma=gamma, kappa=kappa, T=1.0)

    logger.info(
        "LIVE WS + PURE A-S TEST | committed future path | WS=%s | profile=%s | gamma=%.2f kappa=%.2f | duration=%.0fs",
        ws_url,
        profile,
        gamma,
        kappa,
        seconds,
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

    # Start the WS subscription in the background
    ws_task = asyncio.create_task(
        ws_feed.run(
            seconds=seconds,
            http_refresh_seconds=60.0,
            summary_interval_seconds=30.0,
        )
    )

    # Runtime dict for GUI demo / compatibility (populated on each sample)
    gui_runtime: dict = {
        "as_mode": "pure",
        "active_profile": profile,
        "dry_run": True,
        "recent_decisions": [],
    }

    # Start the new real-time A-S HUD (the dedicated live GUI surface for WS + pure A-S)
    if serve_hud and run_hud:
        run_hud(host="127.0.0.1", port=8765, background=True)
        print("   → NEW GUI: Open http://127.0.0.1:8765 in your browser for the dedicated real-time WS + pure A-S HUD")
        print("      (live book + A-S reservation, suggested levels, freshness, recent decisions — updates ~every 800ms)")

    end = time.monotonic() + seconds
    last_sample = 0.0
    last_json_save = 0.0

    try:
        while time.monotonic() < end:
            now = time.monotonic()
            if now - last_sample >= sample_interval:
                await _sample_and_decide(
                    ws_feed,
                    as_strat,
                    profile,
                    xrp_bal,
                    rlusd_bal,
                    target_ratio,
                    verbose=verbose,
                    runtime=gui_runtime,
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
                        "active_profile": gui_runtime.get("active_profile"),
                        "bot_account_address": "r... (from config - see Credentials page)",
                        # Note: secrets are never sent for security; enter in demo fields on Credentials page
                    }
                    hud_update_state(hud_state)

                # Save the runtime JSON frequently while the tester is running
                # so you can load the *current* WS + pure A-S data into the main Streamlit GUI
                # (without waiting for the run to finish). This prevents "lost data".
                # It will overwrite logs/ws_as_demo_runtime.json — the previous longrun data is in
                # logs/runtime_state.json or your vps_ files; this ws_as_demo is specifically for
                # viewing the current tester run in the full base GUI style.
                if now - last_json_save >= 5.0:
                    try:
                        out = Path("logs/ws_as_demo_runtime.json")
                        out.parent.mkdir(parents=True, exist_ok=True)
                        with out.open("w") as f:
                            json.dump(gui_runtime, f, default=str, indent=2)
                        logger.info("Updated logs/ws_as_demo_runtime.json with current WS data — load this in main Streamlit to see full GUI (sidebar, tickers, A-S sections) with live tester data.")
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
    logger.info("GUI demo runtime available in-memory (last state has A-S fields + standard decision_summary for Streamlit/ticker reuse).")

    # Save last gui_runtime for easy loading into the base Streamlit GUI or ticker for side-by-side demo
    try:
        out = Path("logs/ws_as_demo_runtime.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as f:
            json.dump(gui_runtime, f, default=str, indent=2)
        logger.info("Saved GUI demo runtime to %s — load this into streamlit_gui or inspect to see how the existing Base GUI would render the WS + pure A-S decisions (familiar strings + new A-S + WS age fields).", out)
    except Exception as e:
        logger.warning("Could not save demo runtime: %s", e)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Live WS + pure A-S tester (committed future path)")
    parser.add_argument("--seconds", type=float, default=120.0, help="How long to run the live test")
    parser.add_argument("--gamma", type=float, default=0.35, help="A-S gamma (inventory risk aversion) - lower for more presence")
    parser.add_argument("--kappa", type=float, default=3.5, help="A-S kappa (arrival intensity) - higher for tighter/more competitive spreads")
    parser.add_argument("--profile", default="tight_spread", help="Profile for wiring context")
    parser.add_argument("--xrp-bal", type=float, default=138.0, help="Assumed XRP balance for inventory calc")
    parser.add_argument("--rlusd-bal", type=float, default=124.0, help="Assumed RLUSD balance for inventory calc")
    parser.add_argument("--target-ratio", type=float, default=0.55, help="Target XRP ratio")
    parser.add_argument("--sample-interval", type=float, default=8.0, help="Seconds between decision samples")
    parser.add_argument("--verbose", action="store_true", help="Extra WS age / message count logging")
    parser.add_argument("--serve-hud", action="store_true", help="Start the new dedicated real-time WS + pure A-S HUD (http://127.0.0.1:8765) — this is the live 'new gui' surface for the committed path (book + A-S math + WS freshness updating in real time)")
    args = parser.parse_args()

    asyncio.run(
        run_live_test(
            seconds=args.seconds,
            gamma=args.gamma,
            kappa=args.kappa,
            profile=args.profile,
            xrp_bal=args.xrp_bal,
            rlusd_bal=args.rlusd_bal,
            target_ratio=args.target_ratio,
            sample_interval=args.sample_interval,
            verbose=args.verbose,
            serve_hud=args.serve_hud,
        )
    )


if __name__ == "__main__":
    main()
