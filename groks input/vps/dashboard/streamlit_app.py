"""
XLedgerMate VPS Operator Dashboard (read-only monitoring).

Run on the VPS next to the bot repo:
  cd /root/xledgermate
  .venv/bin/streamlit run "groks input/vps/dashboard/streamlit_app.py" --server.address 127.0.0.1 --server.port 8501

From Windows (SSH tunnel):
  ssh -i ~/.ssh/hetzner_xledgermate -L 8501:127.0.0.1:8501 root@188.245.50.229
  Browser: http://localhost:8501
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Allow importing repo utils when dashboard lives inside the clone.
def _find_repo_root() -> Path:
    env = os.environ.get("XLEDGERMATE_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "main.py").exists() and (parent / "config").is_dir():
            return parent
    return Path.cwd().resolve()


REPO_ROOT = _find_repo_root()
LOGS = REPO_ROOT / "logs"
RUNTIME_PATH = LOGS / "runtime_state.json"
KILL_PATH = LOGS / "kill_switch.json"
DECISIONS_PATH = LOGS / "decisions.jsonl"
ENGINE_PID_PATH = LOGS / "engine.pid"
ENGINE_STOP_PATH = LOGS / "engine.stop"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _tail_jsonl(path: Path, limit: int = 40) -> List[Dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def _engine_pid_alive() -> tuple[Optional[int], bool]:
    if not ENGINE_PID_PATH.exists():
        return None, False
    try:
        pid = int(ENGINE_PID_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None, False
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                check=False,
            )
            return pid, True  # weak check on Windows
        except OSError:
            return pid, False
    try:
        os.kill(pid, 0)
        return pid, True
    except OSError:
        return pid, False


def _systemd_engine_status() -> str:
    if sys.platform == "win32":
        return "n/a (Windows host)"
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "xledgermate"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (proc.stdout or proc.stderr or "?").strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "systemctl unavailable"


def _run_skim_report() -> str:
    script = REPO_ROOT / "scripts" / "weekly_skim_report.py"
    if not script.exists():
        return "weekly_skim_report.py not found in repo."
    py = REPO_ROOT / ".venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    try:
        proc = subprocess.run(
            [str(py), str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"Error running report: {exc}"


def _mtime_label(path: Path) -> str:
    if not path.exists():
        return "missing"
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")


st.set_page_config(
    page_title="XLedgerMate VPS Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("XLedgerMate — VPS operator dashboard")
st.caption(f"Repo: `{REPO_ROOT}` · Read-only monitoring (control via SSH / full GUI)")

refresh_sec = st.sidebar.slider("Auto-refresh (seconds)", 5, 120, 15)
if st.sidebar.button("Refresh now"):
    st.rerun()

st.sidebar.markdown("### Access from your PC")
st.sidebar.code(
    "ssh -i ~/.ssh/hetzner_xledgermate -L 8501:127.0.0.1:8501 root@YOUR_VPS_IP",
    language="powershell",
)
st.sidebar.markdown("Then open **http://localhost:8501**")
st.sidebar.markdown("### Paths")
st.sidebar.text(f"Runtime: {RUNTIME_PATH}")
st.sidebar.text(f"Updated: {_mtime_label(RUNTIME_PATH)}")

runtime = _load_json(RUNTIME_PATH)
kill = _load_json(KILL_PATH)
pid, pid_alive = _engine_pid_alive()
systemd = _systemd_engine_status()
kill_active = bool(kill.get("active")) or bool(runtime.get("kill_switch_active"))

col_status = st.columns(5)
with col_status[0]:
    if systemd == "active" or pid_alive:
        st.success("Engine: **running**")
    else:
        st.error("Engine: **stopped**")
    st.caption(f"systemd: {systemd} · pid file: {pid or '—'}")
with col_status[1]:
    if kill_active:
        st.error("Kill switch: **ON**")
    else:
        st.success("Kill switch: **off**")
with col_status[2]:
    st.info(f"Profile: **{runtime.get('active_profile', '—')}**")
with col_status[3]:
    st.metric("Cycles", int(runtime.get("cycle_count") or 0))
with col_status[4]:
    st.metric("Session fills", int(runtime.get("fills_session") or 0))

if kill_active:
    reason = kill.get("reason") or runtime.get("kill_switch_reason") or "unknown"
    st.error(f"Kill reason: {reason}")
    if kill.get("activated_utc"):
        st.caption(f"Activated: {kill.get('activated_utc')}")

if ENGINE_STOP_PATH.exists():
    st.warning("`logs/engine.stop` exists — engine will exit on next cycle.")

# Economics row
e1, e2, e3, e4, e5, e6 = st.columns(6)
with e1:
    st.metric("Portfolio (XRP)", f"{float(runtime.get('portfolio_value_xrp') or 0):.4f}")
with e2:
    st.metric("Balance session PnL", f"{float(runtime.get('session_pnl_balance_xrp') or 0):+.4f} XRP")
with e3:
    st.metric("Toxic ratio", f"{float(runtime.get('toxic_fill_ratio') or 0) * 100:.0f}%")
with e4:
    st.metric("Toxic @30s", f"{float(runtime.get('toxic_fill_ratio_30s') or 0) * 100:.0f}%")
with e5:
    st.metric("Cancel / fill", f"{float(runtime.get('cancel_per_fill') or 0):.2f}")
with e6:
    st.metric("Open offers", int(runtime.get("open_offers_count") or 0))

st.markdown("### Market & policy")
m1, m2, m3 = st.columns(3)
with m1:
    mid = runtime.get("mid_price")
    bid = runtime.get("best_bid_rlusd_per_xrp")
    ask = runtime.get("best_ask_rlusd_per_xrp")
    st.write(
        f"**Mid:** {float(mid):.6f} RLUSD/XRP" if mid else "**Mid:** —",
    )
    if bid and ask:
        st.write(f"Bid {float(bid):.6f} · Ask {float(ask):.6f}")
    st.write(f"Book spread: {float(runtime.get('book_spread_pct') or 0):.3f}%")
    st.write(f"Condition: **{runtime.get('market_condition_label', '—')}**")
with m2:
    st.write(f"**Policy:** {runtime.get('quoting_policy_label') or '—'}")
    st.write(f"Touch mode: `{runtime.get('quoting_touch_mode') or '—'}`")
    st.write(f"Inventory: {runtime.get('inventory_label', '—')}")
    st.write(f"Edge met: {runtime.get('market_edge_met', '—')}")
with m3:
    st.write(f"**Balances:** {float(runtime.get('balance_xrp') or 0):.4f} XRP")
    st.write(f"RLUSD: {float(runtime.get('balance_rlusd') or 0):.4f}")
    st.write(f"Drawdown: {float(runtime.get('drawdown_pct') or 0):.2f}%")
    st.write(f"Last exec: {runtime.get('last_execution_summary') or '—'}")

spread_ok = runtime.get("spread_validation_ok")
if spread_ok is False:
    st.warning(f"Spread check: {runtime.get('spread_validation_summary', 'FAILED')}")
elif spread_ok is True:
    st.success(f"Spread check: {runtime.get('spread_validation_summary', 'OK')}")

# Price history chart
history = runtime.get("price_history") or []
if history:
    import pandas as pd

    df = pd.DataFrame(history)
    if "mid" in df.columns and len(df) > 1:
        st.markdown("### Mid price (engine history)")
        chart_df = df[["mid"]].copy()
        if "ts" in df.columns:
            chart_df.index = df["ts"]
        st.line_chart(chart_df)

# Decisions
st.markdown("### Recent decisions")
decisions = runtime.get("recent_decisions") or []
if not decisions:
    decisions = _tail_jsonl(DECISIONS_PATH, 30)
if decisions:
    import pandas as pd

    ddf = pd.DataFrame(decisions)
    cols = [c for c in ("ts_utc", "ts", "category", "message") if c in ddf.columns]
    if not cols:
        cols = list(ddf.columns)
    st.dataframe(ddf[cols].tail(25), use_container_width=True, hide_index=True)
else:
    st.info("No decisions yet — engine may not have completed a cycle.")

# Open offers
offers = runtime.get("open_offers") or []
if offers:
    st.markdown("### Open offers")
    import pandas as pd

    st.dataframe(pd.DataFrame(offers), use_container_width=True, hide_index=True)

# Quote intents
intents = runtime.get("quote_intents") or []
if intents:
    st.markdown("### Planned quotes (last cycle)")
    import pandas as pd

    st.dataframe(pd.DataFrame(intents), use_container_width=True, hide_index=True)

with st.expander("Full runtime JSON"):
    st.json(runtime)

with st.expander("Weekly skim report (run now)"):
    if st.button("Generate skim report"):
        st.code(_run_skim_report(), language="text")

with st.expander("SSH quick commands"):
    st.code(
        """# Status
sudo systemctl status xledgermate
sudo systemctl status xledgermate-dashboard

# Logs
journalctl -u xledgermate -f

# Clear kill + restart
cd /root/xledgermate && .venv/bin/python main.py --mode clear-kill
sudo systemctl restart xledgermate

# Cancel all offers
.venv/bin/python main.py --mode cancel-offers""",
        language="bash",
    )

st.caption(f"Last runtime file update: {_mtime_label(RUNTIME_PATH)} · Dashboard refresh: {refresh_sec}s")

import time

time.sleep(refresh_sec)
st.rerun()