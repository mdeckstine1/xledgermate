import importlib
import json
import logging
import time
from pathlib import Path

import streamlit as st
import pandas as pd

import config.settings as settings_module
from config.settings import BotConfig
from core.perception import BUILT_IN_PROFILES
from utils.xrpl_currency import RLUSD_ISSUER_TESTNET
from gui.engine_control import (
    cancel_offers_on_ledger,
    clear_kill_switch,
    is_engine_running,
    run_single_cycle,
    start_engine,
    stop_engine,
)

logger = logging.getLogger(__name__)
RUNTIME_STATE_PATH = Path("logs/runtime_state.json")


def _load_runtime_state() -> dict:
    if not RUNTIME_STATE_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def run_gui() -> None:
    st.set_page_config(page_title="XLedgerMate", page_icon="chart", layout="wide")
    st.title("XLedgerMate - XRPL Market Maker")

    importlib.reload(settings_module)
    try:
        config = settings_module.BotConfig.load()
    except TypeError as exc:
        st.error(
            "Config failed to load (stale code in memory). "
            "Fully stop Streamlit and restart with `run.bat`.\n\n"
            f"Details: {exc}"
        )
        st.stop()
    runtime = _load_runtime_state()

    if not config.bot_account_address:
        st.error(
            "Bot account not configured. Enter your **Bot Account** address and secret "
            "in the sidebar under **Bot Account (required)**, then click **Save Config**."
        )

    st.sidebar.header("Bot Account (required)")
    config.bot_account_address = st.sidebar.text_input(
        "Bot Account Address (r...)",
        value=config.bot_account_address,
        placeholder="rYourBotAccountAddress...",
    )
    config.bot_secret_key = st.sidebar.text_input(
        "Bot Secret Key (never commit to git)",
        value=config.bot_secret_key,
        type="password",
        placeholder="s...",
    )
    st.sidebar.caption("Use the dedicated Bot Account only — not your Mangie bag.")

    st.sidebar.header("Risk Capital Settings")
    config.risk_capital_xrp = st.sidebar.number_input(
        "Risk Capital (XRP)", value=config.risk_capital_xrp, step=100.0
    )

    st.sidebar.header("Order Brackets (3-level)")
    config.order_sizes[0] = st.sidebar.number_input(
        "Level 1 Size (XRP)", value=config.order_sizes[0], step=50.0
    )
    config.order_sizes[1] = st.sidebar.number_input(
        "Level 2 Size (XRP)", value=config.order_sizes[1], step=50.0
    )
    config.order_sizes[2] = st.sidebar.number_input(
        "Level 3 Size (XRP)", value=config.order_sizes[2], step=50.0
    )

    st.sidebar.header("Spreads & Timing")
    config.base_spread = (
        st.sidebar.number_input(
            "Base Spread (%)", value=config.base_spread * 100, step=0.01, format="%.2f"
        )
        / 100
    )
    config.order_refresh_time_seconds = st.sidebar.number_input(
        "Refresh Time (seconds)", value=config.order_refresh_time_seconds, step=10
    )
    profile_names = list(BUILT_IN_PROFILES.keys())
    active_idx = (
        profile_names.index(config.active_profile)
        if config.active_profile in profile_names
        else 0
    )
    config.active_profile = st.sidebar.selectbox(
        "Active Profile", options=profile_names, index=active_idx
    )

    st.sidebar.header("XRPL Network")
    config.testnet = st.sidebar.toggle("Use Testnet", value=config.testnet)
    config.xrpl_testnet_rpc_url = st.sidebar.text_input(
        "Testnet RPC URL", value=config.xrpl_testnet_rpc_url
    )
    config.xrpl_mainnet_rpc_url = st.sidebar.text_input(
        "Mainnet RPC URL", value=config.xrpl_mainnet_rpc_url
    )
    private_node = st.sidebar.text_input(
        "Private Node URL (optional)", value=config.private_node_url or ""
    )
    config.private_node_url = private_node or None

    st.sidebar.header("Execution")
    config.dry_run = st.sidebar.toggle("Dry Run (no live orders)", value=config.dry_run)
    config.trading_enabled = st.sidebar.toggle(
        "Trading Enabled", value=config.trading_enabled
    )
    config.rlusd_issuer = st.sidebar.text_input(
        "RLUSD Issuer override (optional)",
        value=config.rlusd_issuer or "",
        help=f"Leave empty to use network default. Testnet: {RLUSD_ISSUER_TESTNET}",
    )
    st.sidebar.caption(f"Active RLUSD issuer: **{config.resolved_rlusd_issuer()}**")

    st.sidebar.header("Risk Management")
    config.max_daily_drawdown_percent = st.sidebar.slider(
        "Daily Max Drawdown (%)",
        min_value=config.min_drawdown_percent,
        max_value=config.max_drawdown_percent,
        value=config.max_daily_drawdown_percent,
        step=0.1,
    )

    if st.sidebar.button("Save Config"):
        config.save()
        st.sidebar.success("Config saved")

    st.header("Bot Control")
    engine_running = is_engine_running()
    if engine_running:
        st.success("Engine status: **RUNNING**")
    else:
        st.warning("Engine status: **STOPPED**")

    col_start, col_stop, col_once = st.columns(3)
    with col_start:
        start_clicked = st.button("Start Bot", type="primary", disabled=engine_running)
    with col_stop:
        stop_clicked = st.button("Stop Bot", disabled=not engine_running)
    with col_once:
        once_clicked = st.button("Run One Cycle")

    col_cancel, col_clear_kill, col_emergency = st.columns(3)
    with col_cancel:
        cancel_offers_clicked = st.button("Cancel All Offers (ledger)")
    with col_clear_kill:
        clear_kill_clicked = st.button("Clear Kill Switch")
    with col_emergency:
        emergency_clicked = st.button("Emergency Stop", type="secondary")

    if start_clicked:
        if not config.bot_account_address.strip():
            st.error("Save your Bot Account address and secret first, then click Start Bot.")
        else:
            config.save()
            ok, msg = start_engine(force_restart=True)
            if ok:
                st.success(msg)
            else:
                st.warning(msg)
            st.rerun()

    if stop_clicked:
        ok, msg = stop_engine()
        if ok:
            st.success(msg)
        else:
            st.warning(msg)
        st.rerun()

    if once_clicked:
        if not config.bot_account_address.strip():
            st.error("Configure Bot Account first, then click Save Config.")
        else:
            config.save()
            with st.spinner("Running one market cycle..."):
                ok, msg = run_single_cycle()
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    if cancel_offers_clicked:
        with st.spinner("Cancelling offers on ledger..."):
            ok, msg = cancel_offers_on_ledger()
        st.success(msg) if ok else st.error(msg)

    if clear_kill_clicked:
        ok, msg = clear_kill_switch()
        st.success(msg) if ok else st.error(msg)

    if emergency_clicked:
        from risk.kill_switch import KillSwitch

        KillSwitch().activate("GUI emergency stop")
        config.trading_enabled = False
        config.save()
        stop_engine()
        if not config.dry_run:
            cancel_offers_on_ledger()
        st.error("Emergency stop: trading disabled, engine stopped, kill switch set.")

    refresh_col, auto_col = st.columns([1, 3])
    if refresh_col.button("Refresh now"):
        st.rerun()
    auto_refresh = auto_col.checkbox(
        "Auto-refresh every 5s while engine is running", value=True
    )

    st.header("Live Bot Status")
    st.write(f"Risk Capital: **{config.risk_capital_xrp:,} XRP**")
    st.write(f"Drawdown Kill-Switch: **{config.max_daily_drawdown_percent}%**")
    st.write(f"Active Profile: **{config.active_profile}**")
    st.write(f"Network: **{config.network_name()}**")
    st.write(f"RPC: **{config.resolved_rpc_url()}**")
    st.write(f"Dry Run: **{config.dry_run}** | Trading Enabled: **{config.trading_enabled}**")
    if config.bot_account_address:
        st.write(f"Bot Account: **{config.bot_account_address[:8]}...{config.bot_account_address[-4:]}**")
    else:
        st.warning("Bot account address is not set — engine cannot run cycles.")

    if runtime:
        st.subheader("Preflight (testnet readiness)")
        if runtime.get("preflight_ready"):
            st.success(runtime.get("preflight_summary", "Preflight OK"))
        else:
            st.error(runtime.get("preflight_summary", "Preflight failed"))
        for err in runtime.get("preflight_errors", []):
            st.error(err)
        for warn in runtime.get("preflight_warnings", []):
            st.warning(warn)
        if runtime.get("kill_switch_active"):
            st.error(f"Kill switch active: {runtime.get('kill_switch_reason', '')}")

        st.subheader("Execution & session P&L")
        mid_raw = runtime.get("mid_price")
        mid_bad = mid_raw is not None and float(mid_raw) > 100.0
        if mid_bad:
            st.error(
                f"Mid price **{float(mid_raw):,.0f}** looks like raw XRPL quality, not RLUSD/XRP. "
                "Click **Stop Bot**, then **Start Bot** (or run `run.bat`) to kill stale engine processes."
            )

        exec_col1, exec_col2, exec_col3, exec_col4 = st.columns(4)
        dry = runtime.get("dry_run", config.dry_run)
        exec_col1.metric(
            "Mode",
            "DRY-RUN" if dry else "LIVE",
            help="Dry-run never submits orders to the ledger.",
        )
        exec_col2.metric("Cycles this session", int(runtime.get("cycle_count", 0)))
        exec_col3.metric(
            "Offers placed (last cycle)",
            int(runtime.get("offers_placed_last_cycle", 0)),
        )
        exec_col4.metric(
            "Open offers on ledger",
            int(runtime.get("open_offers_count", 0)),
        )
        st.caption(runtime.get("last_execution_summary", "No execution data yet."))
        st.write(
            f"Balances: **{runtime.get('balance_xrp', 0):.4f} XRP** | "
            f"**{runtime.get('balance_rlusd', 0):.4f} RLUSD**"
        )
        pnl = float(runtime.get("session_pnl_xrp_estimate", 0.0))
        st.metric(
            "Session P&L estimate (XRP equiv.)",
            f"{pnl:+.4f} XRP",
            help="Balance change since this engine session started (not per-fill accounting).",
        )
        st.metric(
            "Portfolio value",
            f"{float(runtime.get('portfolio_value_xrp', 0)):.4f} XRP equiv.",
        )
        st.metric("Daily drawdown", f"{float(runtime.get('drawdown_pct', 0)):.2f}%")
        st.caption("Portfolio snapshots: `logs/portfolio_snapshots.csv`")
        if dry:
            st.info("**Dry-run is ON** — the bot plans quotes but does **not** place trades or earn P&L on-ledger.")

        st.subheader("Live price (from XRPL order book)")
        bid_v = runtime.get("best_bid_rlusd_per_xrp")
        ask_v = runtime.get("best_ask_rlusd_per_xrp")
        mid_v = runtime.get("mid_price")
        st.caption(
            f"Source: **`{runtime.get('price_source', 'xrpl_book_offers')}`** — "
            f"fetched live each cycle via BookOffers on `{runtime.get('rpc_url', '')}`. "
            "Not hardcoded in the bot."
        )
        if mid_v is not None and not mid_bad:
            t1, t2, t3 = st.columns(3)
            t1.metric("Best bid", f"{float(bid_v):.6f}" if bid_v else "n/a", "RLUSD per XRP")
            t2.metric("Mid", f"{float(mid_v):.6f}", "RLUSD per XRP")
            t3.metric("Best ask", f"{float(ask_v):.6f}" if ask_v else "n/a", "RLUSD per XRP")
            if bid_v and ask_v and float(ask_v) > 0:
                inv_mid = (float(bid_v) + float(ask_v)) / 2.0
                st.caption(
                    f"Implied XRP price: **1 XRP ≈ {float(mid_v):.4f} RLUSD** "
                    f"(book spread {(float(ask_v) - float(bid_v)) / float(ask_v) * 100:.2f}%)"
                )

        history = runtime.get("price_history") or []
        st.subheader("Price history (bot polls)")
        st.caption(
            "XRPL has no built-in candle/ticker API. This chart plots **bid / mid / ask** "
            "from each engine cycle (~refresh interval). On testnet the line often looks flat "
            "because the book rarely changes. Mainnet or faster polling shows more movement."
        )
        if len(history) >= 2:
            hist_df = pd.DataFrame(history)
            hist_df["time"] = pd.to_datetime(hist_df["ts_utc"])
            chart_cols = [c for c in ("bid", "mid", "ask") if c in hist_df.columns]
            st.line_chart(hist_df.set_index("time")[chart_cols], height=220)
        elif len(history) == 1:
            st.line_chart(
                pd.DataFrame([{"mid": history[0].get("mid", 0)}]),
                height=120,
            )
            st.caption("Need at least 2 cycles for a trend line — leave the engine running.")
        else:
            st.info("No price samples yet. Start the engine and wait for a few cycles.")

        st.subheader("Spreads & your quote prices")
        spreads = runtime.get("effective_spreads_pct") or {}
        if mid_v and spreads:
            spread_rows = []
            for level in sorted(spreads.keys(), key=lambda x: int(x)):
                pct = float(spreads[level]) / 100.0
                mid_f = float(mid_v)
                spread_rows.append(
                    {
                        "Level": f"L{level}",
                        "Bot spread %": f"{float(spreads[level]):.3f}",
                        "Bid quote": f"{mid_f * (1 - pct):.6f}",
                        "Ask quote": f"{mid_f * (1 + pct):.6f}",
                    }
                )
            st.dataframe(pd.DataFrame(spread_rows), use_container_width=True, hide_index=True)
        else:
            st.write("Effective spreads:", spreads)

        st.subheader("Market summary")
        if config.testnet or runtime.get("price_is_testnet_book", config.testnet):
            st.info(
                "**Testnet prices** come only from testnet offers on the ledger. "
                "They are **not** live mainnet XRP/RLUSD market prices — testnet liquidity "
                "is thin and often unrealistic. Switch **Use Testnet** off and use a "
                "mainnet Bot Account when you want real market pricing."
            )
        else:
            st.caption(
                "Prices are **RLUSD per 1 XRP**, computed from the live mainnet order book."
            )

        def _fmt_price(value) -> str:
            if value is None:
                return "n/a"
            return f"{float(value):.4f}"

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Mid (RLUSD / XRP)", _fmt_price(runtime.get("mid_price")))
        col2.metric("Best Bid (RLUSD / XRP)", _fmt_price(runtime.get("best_bid_rlusd_per_xrp")))
        col3.metric("Best Ask (RLUSD / XRP)", _fmt_price(runtime.get("best_ask_rlusd_per_xrp")))
        col4.metric("Volatility %", f"{runtime.get('volatility_pct', 0):.2f}")

        spread_ba = None
        bid = runtime.get("best_bid_rlusd_per_xrp")
        ask = runtime.get("best_ask_rlusd_per_xrp")
        if bid is not None and ask is not None and float(ask) > 0:
            spread_ba = ((float(ask) - float(bid)) / float(ask)) * 100.0
        col5, col6 = st.columns(2)
        col5.metric("Book Spread (ask-bid)", f"{spread_ba:.2f}%" if spread_ba is not None else "n/a")
        col6.metric("Liquidity Score", f"{runtime.get('liquidity_score', 0):.2f}")
        st.write(f"Kill Switch: **{runtime.get('kill_switch_active', False)}**")
        intents = runtime.get("quote_intents", [])
        if intents:
            st.write("Quote intents (price = RLUSD per XRP):")
            for q in intents:
                st.caption(
                    f"{q.get('side', '?')} L{q.get('level', '?')}: "
                    f"{float(q.get('price', 0)):.4f} RLUSD/XRP, size {q.get('size', 0)}"
                )
        else:
            st.write("Quote intents: none")
        decisions = runtime.get("recent_decisions", [])
        st.subheader("Recent decisions (newest first)")
        if decisions:
            df = pd.DataFrame(decisions)
            if "ts_utc" in df.columns:
                df = df.sort_values("ts_utc", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.write("No decisions logged yet.")

        if runtime.get("last_error"):
            st.error(runtime["last_error"])
        st.caption(
            f"Last updated: {runtime.get('updated_utc', 'n/a')} | "
            f"Engine PID: {runtime.get('engine_pid', 'n/a')}"
        )
    else:
        st.warning(
            "No runtime snapshot yet. Start engine with "
            "`python main.py --mode engine` or run one cycle with `--mode once`."
        )

    if auto_refresh and engine_running:
        time.sleep(5)
        st.rerun()



if __name__ == "__main__":
    run_gui()
