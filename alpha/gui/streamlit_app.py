"""xLedgerMate Trading Bot Alpha — lightweight operator GUI (Streamlit)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Repo root on sys.path (Streamlit may set cwd to gui/).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import streamlit as st  # noqa: E402

from alpha.operator.activity import ActivityLog  # noqa: E402
from alpha.operator.controls import OperatorControlStore  # noqa: E402
from alpha.runtime.application import AlphaApplication  # noqa: E402
from alpha.version import ALPHA_VERSION  # noqa: E402
from config.settings import BotConfig  # noqa: E402
from risk.kill_switch import KillSwitch  # noqa: E402

LOGS = _REPO / "logs"
KILL_PATH = LOGS / "kill_switch.json"


def _run_cycle(*, execute: bool) -> Dict[str, Any]:
    app, validation = AlphaApplication.from_config_file(state_dir=LOGS)

    async def _inner() -> Dict[str, Any]:
        try:
            if execute:
                result = await app.run_trading_cycle(telegram=False)
            else:
                result = await app.run_status_cycle(telegram=False)
            return {
                "ok": True,
                "validation": validation,
                "report": result.report_text,
                "decision": result.decision.action.value,
                "reason": result.decision.reason,
                "execution": (
                    result.execution.message if result.execution else ""
                ),
                "snapshot": result.snapshot,
                "orders": result.orders,
            }
        finally:
            await app.close()

    return asyncio.run(_inner())


def run_gui() -> None:
    st.set_page_config(
        page_title="xLedgerMate Alpha",
        page_icon="📊",
        layout="wide",
    )
    st.title(f"xLedgerMate Alpha v{ALPHA_VERSION}")
    st.caption("Value accumulation — brackets, inventory, risk. Mainnet: keep dry_run=true until ready.")

    controls = OperatorControlStore(path=LOGS / "alpha_controls.json")
    activity = ActivityLog(path=LOGS / "alpha_activity.jsonl")
    kill = KillSwitch(path=KILL_PATH)

    try:
        cfg = BotConfig.load()
    except Exception as exc:
        st.error(f"Config load failed: {exc}")
        return

    col_mode, col_net, col_dry = st.columns(3)
    col_mode.metric("Trading enabled (yaml)", "yes" if cfg.trading_enabled else "no")
    col_net.metric("Network", "testnet" if cfg.testnet else "mainnet")
    col_dry.metric("dry_run", str(cfg.dry_run))

    ctrl = controls.load()
    if ctrl.trading_paused:
        st.warning(f"Operator PAUSE active: {ctrl.pause_reason or 'paused'}")

    kill_state = kill.reload()
    if kill_state.active:
        st.error(f"Kill switch ACTIVE: {kill_state.reason}")

    st.subheader("Controls")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Refresh status", use_container_width=True):
            st.session_state["last_result"] = _run_cycle(execute=False)
    with c2:
        if st.button("Run one cycle", use_container_width=True):
            st.session_state["last_result"] = _run_cycle(execute=True)
    with c3:
        if st.button("Pause trading", use_container_width=True):
            controls.pause("GUI pause")
            st.rerun()
    with c4:
        if st.button("Resume trading", use_container_width=True):
            controls.resume()
            st.rerun()

    c5, c6 = st.columns(2)
    with c5:
        if st.button("Clear kill switch", use_container_width=True):
            kill.clear("GUI clear")
            st.success("Kill switch cleared")
    with c6:
        if st.button("Reload config view", use_container_width=True):
            st.session_state["config_view"] = BotConfig.load().to_dict()
            st.rerun()

    result: Optional[Dict[str, Any]] = st.session_state.get("last_result")
    if result and result.get("ok"):
        snap = result["snapshot"]
        inv = snap.inventory
        risk = snap.risk
        orders = result["orders"]

        st.subheader("Portfolio")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("XRP", f"{snap.balances.xrp:.4f}")
        m2.metric("RLUSD", f"{snap.balances.rlusd:.4f}")
        m3.metric("Portfolio (XRP eq)", f"{snap.balances.portfolio_xrp_equiv:.4f}")
        m4.metric("Session P&L", f"{risk.session_pnl_xrp:+.4f} XRP")

        st.subheader("Inventory")
        i1, i2, i3 = st.columns(3)
        i1.metric("XRP allocation", f"{inv.xrp_allocation_pct:.1f}%")
        i2.metric("Deviation", f"{inv.deviation:+.3f}")
        i3.metric("Label", inv.label)

        st.subheader("Brackets")
        b1, b2, b3 = st.columns(3)
        b1.metric("Pending buys", orders.pending_buys)
        b2.metric("Active brackets", orders.active_brackets)
        b3.metric("Open offers", len(orders.open_offers))
        if orders.bracket_states:
            st.code("\n".join(orders.bracket_states))

        st.subheader("Risk")
        st.write(risk.preflight_summary)
        st.write(f"Drawdown: {risk.drawdown_pct:.2f}% / {risk.max_drawdown_pct:.2f}%")
        if risk.alerts:
            for alert in risk.alerts:
                st.warning(alert)

        st.subheader("Last decision")
        st.write(f"**{result['decision']}** — {result['reason']}")
        if result.get("execution"):
            st.write(result["execution"])

        with st.expander("Full report"):
            st.text(result.get("report", ""))

    st.subheader("Recent activity")
    rows = activity.tail(25)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No activity yet — run a cycle or start `python -m alpha run`.")

    with st.expander("Config (read-only view — edit config/config.yaml)"):
        if "config_view" not in st.session_state:
            st.session_state["config_view"] = cfg.to_dict()
        safe = {
            k: v
            for k, v in st.session_state["config_view"].items()
            if "secret" not in k.lower() and "token" not in k.lower() and "password" not in k.lower()
        }
        st.json(safe)

    st.caption(
        f"Logs: {LOGS} | CLI: python -m alpha status | python -m alpha run --once"
    )


if __name__ == "__main__":
    run_gui()
