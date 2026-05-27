import json
import logging
from pathlib import Path

import streamlit as st

from config.settings import BotConfig
from core.perception import BUILT_IN_PROFILES
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

    config = BotConfig.load()
    runtime = _load_runtime_state()

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
    config.rlusd_issuer = st.sidebar.text_input("RLUSD Issuer", value=config.rlusd_issuer)

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

    st.header("Live Bot Status")
    st.info(
        "Run the trading engine in a separate terminal: "
        "`python main.py --mode engine`"
    )
    st.write(f"Risk Capital: **{config.risk_capital_xrp:,} XRP**")
    st.write(f"Drawdown Kill-Switch: **{config.max_daily_drawdown_percent}%**")
    st.write(f"Active Profile: **{config.active_profile}**")
    st.write(f"Network: **{config.network_name()}**")
    st.write(f"RPC: **{config.resolved_rpc_url()}**")
    st.write(f"Dry Run: **{config.dry_run}** | Trading Enabled: **{config.trading_enabled}**")

    if runtime:
        st.subheader("Engine Runtime Snapshot")
        col1, col2, col3 = st.columns(3)
        col1.metric("Mid Price", runtime.get("mid_price", "n/a"))
        col2.metric("Volatility %", f"{runtime.get('volatility_pct', 0):.2f}")
        col3.metric("Liquidity Score", f"{runtime.get('liquidity_score', 0):.2f}")
        st.write(f"Balance (XRP): **{runtime.get('balance_xrp', 0):.4f}**")
        st.write(f"Open Offers: **{runtime.get('open_offers_count', 0)}**")
        st.write(f"Kill Switch: **{runtime.get('kill_switch_active', False)}**")
        st.write("Effective spreads:", runtime.get("effective_spreads_pct", {}))
        st.write("Quote intents:", runtime.get("quote_intents", []))
        st.write("Recent decisions:", runtime.get("recent_decisions", []))
        if runtime.get("last_error"):
            st.error(runtime["last_error"])
        st.caption(f"Last updated: {runtime.get('updated_utc', 'n/a')}")
    else:
        st.warning(
            "No runtime snapshot yet. Start engine with "
            "`python main.py --mode engine` or run one cycle with `--mode once`."
        )

    if st.button("Emergency Stop (config)"):
        config.trading_enabled = False
        config.save()
        st.error("Trading disabled in config. Engine will stop placing orders on next cycle.")


if __name__ == "__main__":
    run_gui()
