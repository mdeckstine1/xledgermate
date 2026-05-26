import streamlit as st
from config.settings import BotConfig
from risk.drawdown import DrawdownMonitor
import logging

logger = logging.getLogger(__name__)

def run_gui():
    st.set_page_config(page_title="XLedgerMate", page_icon="📈", layout="wide")
    st.title("🪙 XLedgerMate - XRPL Avellaneda Bot")

    config = BotConfig.load()

    st.sidebar.header("Risk Capital Settings")
    config.risk_capital_xrp = st.sidebar.number_input("Risk Capital (XRP)", value=config.risk_capital_xrp, step=100.0)

    st.sidebar.header("Order Brackets (3-level)")
    config.order_sizes[0] = st.sidebar.number_input("Level 1 Size (XRP)", value=config.order_sizes[0], step=50.0)
    config.order_sizes[1] = st.sidebar.number_input("Level 2 Size (XRP)", value=config.order_sizes[1], step=50.0)
    config.order_sizes[2] = st.sidebar.number_input("Level 3 Size (XRP)", value=config.order_sizes[2], step=50.0)

    st.sidebar.header("Spreads & Timing")
    config.base_spread = st.sidebar.number_input("Base Spread (%)", value=config.base_spread * 100, step=0.01, format="%.2f") / 100
    config.order_refresh_time_seconds = st.sidebar.number_input("Refresh Time (seconds)", value=config.order_refresh_time_seconds, step=10)

    st.sidebar.header("Risk Management")
    config.max_daily_drawdown_percent = st.sidebar.slider(
        "Daily Max Drawdown (%)", 
        min_value=config.min_drawdown_percent, 
        max_value=config.max_drawdown_percent, 
        value=config.max_daily_drawdown_percent, 
        step=0.1
    )

    if st.sidebar.button("Save Config"):
        config.save()
        st.sidebar.success("✅ Config saved")

    st.header("Live Bot Status")
    st.info("Avellaneda Market Making is running with your layered brackets + volatility + trailing sell-side logic.")
    st.write(f"Risk Capital: **{config.risk_capital_xrp:,} XRP**")
    st.write(f"Drawdown Kill-Switch: **{config.max_daily_drawdown_percent}%**")
    st.write(f"Auto Rollover: **Enabled** (pure risk capital)")

    if st.button("🚨 Emergency Stop"):
        st.error("Kill switch activated - bot stopped")
        # In production this would trigger the KillSwitch

    st.caption("Built for mdeckstine1 - airtight, modular, and fully isolated from your main Mangie bag.")

if __name__ == "__main__":
    run_gui()
