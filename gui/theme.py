"""XLedgerMate GUI theme — dark professional trading desk styling."""

from __future__ import annotations

from typing import Optional


def inject_theme() -> None:
    """Apply global dark theme and component styling."""
    import streamlit as st

    st.markdown(
        """
        <style>
        /* ── Base palette ── */
        :root {
            --xlm-bg: #0b0e14;
            --xlm-surface: #131722;
            --xlm-surface-2: #1a2030;
            --xlm-border: #2a3142;
            --xlm-text: #e6eaf2;
            --xlm-muted: #8b93a7;
            --xlm-green: #3dd68c;
            --xlm-red: #f07178;
            --xlm-amber: #ffcc66;
            --xlm-blue: #6cb6ff;
        }

        .stApp {
            background-color: var(--xlm-bg);
            color: var(--xlm-text);
        }

        section[data-testid="stSidebar"] {
            background-color: var(--xlm-surface);
            border-right: 1px solid var(--xlm-border);
        }

        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] label {
            color: var(--xlm-text);
        }

        /* ── Header bar ── */
        .xlm-header {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap;
            align-items: center;
            align-content: center;
            gap: 0.75rem 1.25rem;
            padding: 0.85rem 1.1rem;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, var(--xlm-surface) 0%, var(--xlm-surface-2) 100%);
            border: 1px solid var(--xlm-border);
            border-radius: 10px;
            width: 100%;
            box-sizing: border-box;
        }

        .xlm-header > * {
            flex-shrink: 0;
        }

        .xlm-header-brand {
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: var(--xlm-text);
            margin-right: 0.5rem;
        }

        .xlm-header-brand span {
            color: var(--xlm-blue);
        }

        .xlm-pill {
            display: inline-flex !important;
            flex-direction: row !important;
            align-items: center;
            white-space: nowrap;
            padding: 0.28rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            border: 1px solid var(--xlm-border);
            background: var(--xlm-surface-2);
            color: var(--xlm-muted);
        }

        .xlm-pill-running { border-color: #2d6a4f; color: var(--xlm-green); background: #132218; }
        .xlm-pill-stopped { border-color: #6b4f2a; color: var(--xlm-amber); background: #1a1608; }
        .xlm-pill-dry { border-color: #2a4a6b; color: var(--xlm-blue); background: #0f1824; }
        .xlm-pill-live { border-color: #6b2a2a; color: var(--xlm-red); background: #1a0f0f; }
        .xlm-pill-favorable { border-color: #2d6a4f; color: var(--xlm-green); }
        .xlm-pill-defensive { border-color: #6b4f2a; color: var(--xlm-amber); }
        .xlm-pill-hostile { border-color: #6b2a2a; color: var(--xlm-red); }

        .xlm-stat {
            display: inline-flex !important;
            flex-direction: column !important;
            min-width: 5.5rem;
            white-space: nowrap;
        }

        .xlm-stat-label {
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--xlm-muted);
            margin-bottom: 0.15rem;
        }

        .xlm-stat-value {
            font-size: 1.05rem;
            font-weight: 650;
            color: var(--xlm-text);
            font-variant-numeric: tabular-nums;
        }

        .xlm-stat-value.positive { color: var(--xlm-green); }
        .xlm-stat-value.negative { color: var(--xlm-red); }

        .xlm-alert {
            padding: 0.55rem 0.85rem;
            border-radius: 8px;
            margin-bottom: 0.75rem;
            font-size: 0.88rem;
            border-left: 3px solid;
        }

        .xlm-alert-warn {
            background: #1a1608;
            border-color: var(--xlm-amber);
            color: #e8dcc0;
        }

        .xlm-alert-danger {
            background: #1a0f0f;
            border-color: var(--xlm-red);
            color: #f5d0d0;
        }

        .xlm-alert-info {
            background: #0f1824;
            border-color: var(--xlm-blue);
            color: #c8dff5;
        }

        .xlm-card {
            background: var(--xlm-surface);
            border: 1px solid var(--xlm-border);
            border-radius: 10px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.75rem;
        }

        .xlm-card-title {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            color: var(--xlm-muted);
            margin-bottom: 0.65rem;
            font-weight: 600;
        }

        /* ── Metrics ── */
        div[data-testid="stMetric"] {
            background: var(--xlm-surface);
            border: 1px solid var(--xlm-border);
            border-radius: 8px;
            padding: 0.65rem 0.85rem;
        }

        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            text-align: left;
            justify-content: flex-start;
        }

        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: var(--xlm-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.35rem;
            font-weight: 700;
            color: var(--xlm-text);
        }

        /* ── Tabs ── */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            background: transparent;
            border-bottom: 1px solid var(--xlm-border);
        }

        .stTabs [data-baseweb="tab"] {
            background: transparent;
            border-radius: 6px 6px 0 0;
            color: var(--xlm-muted);
            font-weight: 600;
            padding: 0.5rem 1rem;
        }

        .stTabs [aria-selected="true"] {
            background: var(--xlm-surface);
            color: var(--xlm-text);
            border: 1px solid var(--xlm-border);
            border-bottom: none;
        }

        /* ── Expanders in Controls ── */
        details[data-testid="stExpander"] {
            background: var(--xlm-surface);
            border: 1px solid var(--xlm-border);
            border-radius: 8px;
        }

        /* ── Dataframes ── */
        [data-testid="stDataFrame"] {
            border: 1px solid var(--xlm-border);
            border-radius: 8px;
        }

        hr {
            border-color: var(--xlm-border);
            opacity: 0.5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def pnl_class(value: float) -> str:
    if value > 0.0001:
        return "positive"
    if value < -0.0001:
        return "negative"
    return ""


def format_pnl(value: float, *, suffix: str = " XRP") -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.4f}{suffix}"


def header_stat(label: str, value: str, *, value_class: str = "") -> str:
    value_cls = f"xlm-stat-value {value_class}".strip()
    return (
        f'<div class="xlm-stat">'
        f'<div class="xlm-stat-label">{label}</div>'
        f'<div class="{value_cls}">{value}</div>'
        f"</div>"
    )


def pill(text: str, variant: str = "") -> str:
    v = f" xlm-pill-{variant}" if variant else ""
    return f'<span class="xlm-pill{v}">{text}</span>'


def alert_box(message: str, kind: str = "info") -> str:
    return f'<div class="xlm-alert xlm-alert-{kind}">{message}</div>'


def market_pill_variant(condition: str) -> str:
    mapping = {
        "favorable": "favorable",
        "neutral": "",
        "defensive": "defensive",
        "hostile": "hostile",
    }
    return mapping.get(str(condition).lower(), "")


def render_header_bar(
    *,
    engine_running: bool,
    dry_run: bool,
    testnet: bool,
    profile_label: str,
    operating_mode_label: str = "Market make",
    market_label: str,
    market_condition: str,
    pnl_mtm: float,
    pnl_balance: float,
    portfolio_xrp: Optional[float],
    mid: Optional[float],
    network: str,
    fills_session: int = 0,
) -> None:
    """Single top command bar — status, mode, P&L, profile, market."""
    import streamlit as st

    status_pill = pill("Running" if engine_running else "Stopped", "running" if engine_running else "stopped")
    if dry_run:
        mode_pill = pill("Dry Run", "dry")
    elif testnet:
        mode_pill = pill("Testnet Live", "live")
    else:
        mode_pill = pill("Mainnet Live", "live")

    mkt_var = market_pill_variant(market_condition)
    market_pill_html = pill(market_label, mkt_var) if market_label else ""

    port_str = f"{portfolio_xrp:.2f}" if portfolio_xrp is not None else "—"
    mid_str = f"{float(mid):.4f}" if mid is not None else "—"

    stats = "".join(
        [
            header_stat("Portfolio", f"{port_str} XRP"),
            header_stat("Session P&L", format_pnl(pnl_mtm), value_class=pnl_class(pnl_mtm)),
            header_stat("Balance Δ", format_pnl(pnl_balance), value_class=pnl_class(pnl_balance)),
            header_stat("Profile", profile_label),
            header_stat("Mode", operating_mode_label),
            header_stat("Mid", mid_str),
            header_stat("Fills", str(int(fills_session))),
        ]
    )

    html = f"""
    <div class="xlm-header">
        <div class="xlm-header-brand">XLedger<span>Mate</span></div>
        {status_pill}
        {mode_pill}
        {market_pill_html}
        {stats}
        <div class="xlm-stat"><div class="xlm-stat-label">Network</div>
        <div class="xlm-stat-value">{network.upper()}</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
