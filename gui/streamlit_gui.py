"""XLedgerMate Streamlit control panel — tabbed layout with reduced refresh flicker."""

from __future__ import annotations

import importlib
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

import config.settings as settings_module
from config.settings import BotConfig
from core.perception import BUILT_IN_PROFILES
from gui.engine_control import (
    cancel_offers_on_ledger,
    clear_kill_switch,
    is_engine_running,
    run_single_cycle,
    send_funds,
    setup_trust_line as run_setup_trust,
    start_engine,
    stop_engine,
)
from utils.xrpl_currency import RLUSD_ISSUER_TESTNET

logger = logging.getLogger(__name__)
RUNTIME_STATE_PATH = Path("logs/runtime_state.json")
LOGO_PATH = Path(__file__).resolve().parent.parent / "Xledermate.jpg"

try:
    _fragment = st.fragment
except AttributeError:  # pragma: no cover - older Streamlit

    def _fragment(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator


def _load_runtime_state() -> dict:
    if not RUNTIME_STATE_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_config() -> BotConfig:
    importlib.reload(settings_module)
    return settings_module.BotConfig.load()


def _render_brand_logo(*, sidebar: bool = False) -> None:
    if not LOGO_PATH.is_file():
        if sidebar:
            st.markdown("### XLedgerMate")
        else:
            st.title("XLedgerMate")
        return
    if sidebar:
        st.image(str(LOGO_PATH), use_container_width=True)
    else:
        st.image(str(LOGO_PATH), width=480)


def _fmt_price(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _fmt_xrp_balance(value: Any) -> str:
    return f"{float(value or 0):,.2f}"


def _fmt_rlusd_balance(value: Any) -> str:
    return f"{float(value or 0):,.4f}"


def _render_balance_card(column: Any, runtime: dict) -> None:
    """XRP on the main line; RLUSD on a smaller line below (fits narrow columns)."""
    with column:
        st.metric("Balance", _fmt_xrp_balance(runtime.get("balance_xrp")), help="Bot account XRP")
        st.caption(f"RLUSD {_fmt_rlusd_balance(runtime.get('balance_rlusd'))}")


def _quote_table(intents: List[dict]) -> pd.DataFrame:
    rows: Dict[int, dict] = {}
    for q in intents:
        level = int(q.get("level", 0))
        row = rows.setdefault(level, {"Level": f"L{level}"})
        side = str(q.get("side", "")).lower()
        price = float(q.get("price", 0))
        size = float(q.get("size", 0))
        if side == "bid":
            row["Bid price"] = f"{price:.6f}"
            row["Bid size (XRP)"] = f"{size:.2f}"
        elif side == "ask":
            row["Ask price"] = f"{price:.6f}"
            row["Ask size (XRP)"] = f"{size:.2f}"
    if not rows:
        return pd.DataFrame(columns=["Level", "Bid price", "Bid size (XRP)", "Ask price", "Ask size (XRP)"])
    return pd.DataFrame([rows[k] for k in sorted(rows.keys())])


def _render_header(config: BotConfig, runtime: dict, engine_running: bool) -> None:
    mid = runtime.get("mid_price")
    pnl = float(runtime.get("session_pnl_xrp_estimate", 0.0))
    dry = runtime.get("dry_run", config.dry_run)

    h1, h2, h3, h4, h5, h6 = st.columns([1.2, 1, 1, 1, 1, 1])
    status = "RUNNING" if engine_running else "STOPPED"
    h1.markdown(f"**Bot** :{'green' if engine_running else 'orange'}[{status}]")
    h2.markdown(f"**Mode** {'DRY-RUN' if dry else 'LIVE'}")
    h3.metric("Mid", _fmt_price(mid) if mid else "—", help="RLUSD per XRP")
    h4.metric("XRP", _fmt_xrp_balance(runtime.get("balance_xrp")))
    h5.metric("RLUSD", _fmt_rlusd_balance(runtime.get("balance_rlusd")))
    delta_color = "normal" if pnl == 0 else ("normal" if pnl > 0 else "inverse")
    h6.metric("Session P&L", f"{pnl:+.4f}", help="XRP equiv.", delta_color=delta_color)
    st.caption(
        f"{config.network_name().upper()} · {config.active_profile} · "
        f"Updated {runtime.get('updated_utc', 'n/a')}"
    )


def _update_live_dashboard(config: BotConfig) -> None:
    """Refresh live metrics inside the Dashboard tab panel only."""
    runtime = _load_runtime_state()
    engine_running = is_engine_running()

    if not runtime:
        st.info("Start the bot or run one cycle to populate live data.")
        return

    pnl = float(runtime.get("session_pnl_xrp_estimate", 0.0))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Bot status", "RUNNING" if engine_running else "STOPPED")
    _render_balance_card(k2, runtime)
    k3.metric("Drawdown", f"{float(runtime.get('drawdown_pct', 0)):.2f}%")
    k4.metric("Session P&L", f"{pnl:+.4f} XRP")

    mid_raw = runtime.get("mid_price")
    mid_bad = mid_raw is not None and float(mid_raw) > 100.0
    if mid_bad:
        st.error("Invalid mid price — restart engine with `run.bat`.")

    c1, c2, c3, c4 = st.columns(4)
    dry = runtime.get("dry_run", config.dry_run)
    c1.metric("Execution", "DRY-RUN" if dry else "LIVE")
    c2.metric("Cycles", int(runtime.get("cycle_count", 0)))
    c3.metric("Placed (last)", int(runtime.get("offers_placed_last_cycle", 0)))
    c4.metric("Open offers", int(runtime.get("open_offers_count", 0)))
    st.caption(runtime.get("last_execution_summary", ""))

    st.markdown("### Live price (RLUSD / XRP)")
    p1, p2, p3 = st.columns(3)
    bid = runtime.get("best_bid_rlusd_per_xrp")
    ask = runtime.get("best_ask_rlusd_per_xrp")
    p1.metric("Best bid", _fmt_price(bid, 6))
    p2.metric("Mid", _fmt_price(mid_raw, 6))
    p3.metric("Best ask", _fmt_price(ask, 6))

    st.markdown("### Quote ladder (current cycle)")
    intents = runtime.get("quote_intents", [])
    st.dataframe(_quote_table(intents), use_container_width=True, hide_index=True)

    if runtime.get("preflight_ready"):
        st.success(runtime.get("preflight_summary", "Preflight OK"))
    elif "preflight_ready" in runtime:
        st.error(runtime.get("preflight_summary", "Preflight failed"))
    for w in runtime.get("preflight_warnings") or []:
        st.warning(w)


@_fragment(run_every=timedelta(seconds=5))
def _live_dashboard_fragment() -> None:
    panel = st.session_state.get("_dash_live_panel")
    cfg = st.session_state.get("_dash_config")
    if panel is None or cfg is None:
        return
    with panel.container():
        _update_live_dashboard(cfg)


def _render_bot_controls(config: BotConfig) -> None:
    engine_running = is_engine_running()
    c1, c2, c3 = st.columns(3)
    if c1.button("Start Bot", type="primary", disabled=engine_running, use_container_width=True):
        if config.bot_account_address.strip():
            config.save()
            ok, msg = start_engine(force_restart=True)
            st.success(msg) if ok else st.warning(msg)
            st.rerun()
        else:
            st.error("Configure Bot Account first.")
    if c2.button("Stop Bot", disabled=not engine_running, use_container_width=True):
        ok, msg = stop_engine()
        st.success(msg) if ok else st.warning(msg)
        st.rerun()
    if c3.button("Run One Cycle", use_container_width=True):
        config.save()
        with st.spinner("Running cycle..."):
            ok, msg = run_single_cycle()
        st.success(msg) if ok else st.error(msg)


def _render_controls_tab(config: BotConfig) -> None:
    st.markdown("### Order bracket sizes (XRP)")
    st.caption("Three layered quote sizes — adjust with sliders, then **Save Config** in the sidebar.")
    c1, c2, c3 = st.columns(3)
    with c1:
        config.order_sizes[0] = st.slider(
            "Level 1",
            min_value=0.0,
            max_value=float(max(config.risk_capital_xrp, 100.0)),
            value=float(config.order_sizes[0]),
            step=10.0,
        )
    with c2:
        config.order_sizes[1] = st.slider(
            "Level 2",
            min_value=0.0,
            max_value=float(max(config.risk_capital_xrp, 100.0)),
            value=float(config.order_sizes[1]),
            step=25.0,
        )
    with c3:
        config.order_sizes[2] = st.slider(
            "Level 3",
            min_value=0.0,
            max_value=float(max(config.risk_capital_xrp, 100.0)),
            value=float(config.order_sizes[2]),
            step=50.0,
        )

    st.markdown("### Spreads & timing")
    s1, s2, s3 = st.columns(3)
    with s1:
        config.base_spread = st.number_input(
            "Base spread (%)",
            value=config.base_spread * 100,
            step=0.01,
            format="%.2f",
        ) / 100
    with s2:
        config.order_refresh_time_seconds = st.number_input(
            "Refresh interval (sec)",
            value=int(config.order_refresh_time_seconds),
            step=10,
            min_value=15,
        )
    with s3:
        profile_names = list(BUILT_IN_PROFILES.keys())
        idx = profile_names.index(config.active_profile) if config.active_profile in profile_names else 0
        config.active_profile = st.selectbox("Active profile", profile_names, index=idx)

    st.markdown("### Risk & execution flags")
    r1, r2, r3 = st.columns(3)
    with r1:
        config.risk_capital_xrp = st.number_input(
            "Risk capital (XRP)", value=config.risk_capital_xrp, step=100.0
        )
    with r2:
        config.max_daily_drawdown_percent = st.slider(
            "Max daily drawdown (%)",
            min_value=config.min_drawdown_percent,
            max_value=config.max_drawdown_percent,
            value=config.max_daily_drawdown_percent,
            step=0.1,
        )
    with r3:
        config.fund_with_xrp_only = st.toggle(
            "Fund with XRP only",
            value=getattr(config, "fund_with_xrp_only", True),
        )

    e1, e2 = st.columns(2)
    with e1:
        config.dry_run = st.toggle("Dry run (no ledger orders)", value=config.dry_run)
    with e2:
        config.trading_enabled = st.toggle("Trading enabled", value=config.trading_enabled)


def _render_account_tab(config: BotConfig, runtime: dict) -> None:
    st.markdown("### Bot account credentials")
    config.bot_account_address = st.text_input(
        "Bot account address (r...)",
        value=config.bot_account_address,
        placeholder="rYourBotAccountAddress...",
    )
    config.bot_secret_key = st.text_input(
        "Bot secret (never commit)",
        value=config.bot_secret_key,
        type="password",
    )
    st.caption("Dedicated Bot Account only — not your main wallet.")

    st.markdown("### Fund the bot")
    st.info(
        "Send **XRP** to the address below (testnet faucet or transfer). "
        "Use [tryrlusd.com](https://tryrlusd.com) with the **same** address for test RLUSD."
    )
    if config.bot_account_address:
        st.code(config.bot_account_address)
        f1, f2, f3 = st.columns(3)
        if f2.button("Setup RLUSD trust line"):
            if not config.bot_secret_key.strip():
                st.error("Save bot secret first.")
            else:
                with st.spinner("Submitting TrustSet..."):
                    ok, msg = run_setup_trust()
                st.success(msg) if ok else st.error(msg)
        f3.link_button("Get testnet RLUSD", "https://tryrlusd.com/")

    trust_ok = any(
        "trust line exists" in str(c).lower()
        for c in (runtime.get("preflight_summary", ""), *(runtime.get("preflight_warnings") or []))
    ) or bool(runtime.get("preflight_ready"))
    if runtime.get("balance_rlusd") is not None or runtime:
        rlusd_bal = float(runtime.get("balance_rlusd", 0))
        if rlusd_bal > 0 or trust_ok:
            st.success(f"RLUSD on ledger: **{rlusd_bal:.4f}**")
        else:
            st.warning("RLUSD trust line may exist; balance still **0** until faucet pays you.")

    st.markdown("### Send / withdraw")
    send_dest = st.text_input(
        "Send to address",
        value=getattr(config, "send_destination_default", "") or "",
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        send_amount = st.number_input("Amount", min_value=0.0, value=0.0, step=1.0)
    with sc2:
        send_asset = st.selectbox("Asset", ["XRP", "RLUSD"])
    send_ok = st.checkbox("Bot stopped & offers cancelled")
    if st.button("Send now", type="primary"):
        if not config.bot_secret_key.strip():
            st.error("Bot secret required.")
        elif is_engine_running() and not send_ok:
            st.error("Stop bot and confirm checkbox.")
        elif send_amount <= 0:
            st.error("Enter amount > 0.")
        else:
            config.send_destination_default = send_dest.strip()
            config.save()
            with st.spinner("Sending..."):
                ok, msg = send_funds(send_dest.strip(), send_amount, send_asset)
            st.success(msg) if ok else st.error(msg)


def _render_advanced_tab(config: BotConfig, runtime: dict) -> None:
    st.markdown("### Network")
    config.testnet = st.toggle("Use testnet", value=config.testnet)
    config.xrpl_testnet_rpc_url = st.text_input("Testnet RPC", value=config.xrpl_testnet_rpc_url)
    config.xrpl_mainnet_rpc_url = st.text_input("Mainnet RPC", value=config.xrpl_mainnet_rpc_url)
    private = st.text_input("Private node (optional)", value=config.private_node_url or "")
    config.private_node_url = private or None
    config.rlusd_issuer = st.text_input(
        "RLUSD issuer override",
        value=config.rlusd_issuer or "",
        help=f"Default testnet: {RLUSD_ISSUER_TESTNET}",
    )
    st.caption(f"Active issuer: `{config.resolved_rlusd_issuer()}`")

    st.markdown("### Telegram")
    config.telegram_enabled = st.toggle("Enable Telegram", value=config.telegram_enabled)
    config.telegram_token = st.text_input("Bot token", value=config.telegram_token, type="password")
    config.telegram_chat_id = st.text_input("Chat ID", value=config.telegram_chat_id)
    config.telegram_notify_each_cycle = st.toggle(
        "Notify each cycle",
        value=getattr(config, "telegram_notify_each_cycle", False),
    )
    if st.button("Send Telegram test"):
        from monitoring.telegram_alerts import TelegramAlerts

        ok, msg = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=True,
        ).send_test()
        st.success(msg) if ok else st.error(msg)

    st.markdown("### Safety & logs")
    if runtime.get("kill_switch_active"):
        st.error(f"Kill switch active: {runtime.get('kill_switch_reason', '')}")
    else:
        st.success("Kill switch inactive")

    a1, a2, a3 = st.columns(3)
    if a1.button("Clear kill switch"):
        ok, msg = clear_kill_switch()
        st.success(msg) if ok else st.error(msg)
    if a2.button("Cancel all offers"):
        with st.spinner("Cancelling..."):
            ok, msg = cancel_offers_on_ledger()
        st.success(msg) if ok else st.error(msg)
    if a3.button("Emergency stop"):
        from risk.kill_switch import KillSwitch

        KillSwitch().activate("GUI emergency stop")
        config.trading_enabled = False
        config.save()
        stop_engine()
        if not config.dry_run:
            cancel_offers_on_ledger()
        st.error("Emergency stop executed.")

    st.markdown("### Log files")
    st.code(
        "logs/runtime_state.json\nlogs/portfolio_snapshots.csv\n"
        "logs/trades_YYYY-MM.csv (fills, transfers, major events)\n"
        "logs/decisions.jsonl\nlogs/transfers.csv",
        language=None,
    )


def _render_history_tab(config: BotConfig, runtime: dict) -> None:
    if not runtime:
        st.warning("No runtime data yet.")
        return

    st.markdown("### Session statistics")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Portfolio (XRP equiv.)", f"{float(runtime.get('portfolio_value_xrp', 0)):.4f}")
    s2.metric("Drawdown %", f"{float(runtime.get('drawdown_pct', 0)):.2f}")
    s3.metric("Volatility %", f"{float(runtime.get('volatility_pct', 0)):.2f}")
    s4.metric("Liquidity score", f"{float(runtime.get('liquidity_score', 0)):.2f}")

    st.markdown("### Price history")
    history = runtime.get("price_history") or []
    if len(history) >= 2:
        hist_df = pd.DataFrame(history)
        hist_df["time"] = pd.to_datetime(hist_df["ts_utc"], utc=True)
        cols = [c for c in ("bid", "mid", "ask") if c in hist_df.columns]
        chart_df = hist_df.set_index("time")[cols].apply(pd.to_numeric, errors="coerce")
        chart_df = chart_df.dropna(how="all")
        if len(chart_df) >= 2 and not chart_df.empty:
            st.line_chart(chart_df, height=280)
        else:
            st.info("Collecting price samples — chart appears after a few cycles.")
    elif len(history) == 1:
        h0 = history[0]
        st.metric("Latest mid", _fmt_price(h0.get("mid"), 6))
        st.caption("Chart needs at least 2 engine cycles.")
    else:
        st.info("No price samples yet. Start the engine and wait for cycles.")

    st.markdown("### Effective spreads")
    spreads = runtime.get("effective_spreads_pct") or {}
    mid = runtime.get("mid_price")
    if mid and spreads:
        rows = []
        for level in sorted(spreads.keys(), key=lambda x: int(x)):
            pct = float(spreads[level]) / 100.0
            m = float(mid)
            rows.append(
                {
                    "Level": f"L{level}",
                    "Spread %": f"{float(spreads[level]):.3f}",
                    "Bid": f"{m * (1 - pct):.6f}",
                    "Ask": f"{m * (1 + pct):.6f}",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("### Recent decisions")
    decisions = runtime.get("recent_decisions", [])
    if decisions:
        df = pd.DataFrame(decisions)
        if "ts_utc" in df.columns:
            df = df.sort_values("ts_utc", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True, height=320)
    if runtime.get("last_error"):
        st.error(runtime["last_error"])


def run_gui() -> None:
    st.set_page_config(
        page_title="XLedgerMate",
        page_icon=str(LOGO_PATH) if LOGO_PATH.is_file() else "chart",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    try:
        config = _load_config()
    except TypeError as exc:
        st.error(f"Config load failed: {exc}")
        st.stop()

    runtime = _load_runtime_state()
    engine_running = is_engine_running()

    with st.sidebar:
        _render_brand_logo(sidebar=True)
        if st.button("Save Config", type="primary", use_container_width=True):
            config.save()
            st.success("Saved")
        st.divider()
        auto_refresh = st.toggle(
            "Live refresh (5s)",
            value=st.session_state.get("auto_refresh", True),
            help="Updates Dashboard header & metrics only — not the whole page.",
        )
        st.session_state.auto_refresh = auto_refresh
        if st.button("Refresh now", use_container_width=True):
            st.rerun()
        st.caption(f"Network: **{config.network_name()}**")

    _render_brand_logo()
    if not config.bot_account_address:
        st.warning("Set your Bot Account on the **Bot Account** tab, then **Save Config**.")

    _render_header(config, runtime, engine_running)

    tab_dash, tab_ctrl, tab_acct, tab_adv, tab_hist = st.tabs(
        ["Dashboard", "Controls", "Bot Account", "Advanced", "History"]
    )

    with tab_dash:
        _render_bot_controls(config)
        st.session_state._dash_live_panel = st.empty()
        st.session_state._dash_config = config
        if st.session_state.get("auto_refresh", True):
            _live_dashboard_fragment()
        else:
            with st.session_state._dash_live_panel.container():
                _update_live_dashboard(config)

    with tab_ctrl:
        _render_controls_tab(config)

    with tab_acct:
        _render_account_tab(config, runtime)

    with tab_adv:
        _render_advanced_tab(config, runtime)

    with tab_hist:
        _render_history_tab(config, runtime)


if __name__ == "__main__":
    run_gui()
