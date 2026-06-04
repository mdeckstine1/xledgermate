"""Session insights from runtime_state + trades CSV for the Dashboard."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SessionInsights:
    """Fill economics and operator hints for the current engine session."""

    status: str  # ok | cautious | defensive
    headline: str
    window_label: str
    fill_count: int
    buy_count: int
    sell_count: int
    buy_xrp: float
    sell_xrp: float
    net_xrp: float
    capture_xrp: float
    negative_capture_count: int
    capture_per_fill_xrp: float
    xrp_share_pct: float
    target_xrp_share_pct: float
    inventory_deviation_pct: float
    engine_fills: int
    suggestions: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


def _load_trade_rows(logs_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not logs_dir.is_dir():
        return rows
    files = sorted(logs_dir.glob("trades_*.csv"), key=lambda p: p.stat().st_mtime)
    for path in files:
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(list(csv.DictReader(handle)))
        except (OSError, csv.Error):
            continue
    return rows


def _last_engine_start_index(rows: Sequence[dict[str, str]]) -> int:
    for idx in range(len(rows) - 1, -1, -1):
        row = rows[idx]
        if row.get("event_type") == "MAJOR" and "Engine started" in (row.get("notes") or ""):
            return idx
    return 0


def _fill_rows(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        side = (row.get("side") or row.get("event_type") or "").strip().upper()
        if side in ("BUY", "SELL"):
            out.append(row)
    return out


def _volume_and_capture(fills: Sequence[dict[str, str]]) -> tuple[float, float, float, float, int]:
    buy_xrp = sell_xrp = 0.0
    buy_cap = sell_cap = 0.0
    negative = 0
    for row in fills:
        amt = float(row.get("xrp_amount") or 0)
        cap = float(row.get("profit_xrp_equiv") or 0)
        side = (row.get("side") or "").upper()
        if side == "BUY":
            buy_xrp += amt
            buy_cap += cap
        elif side == "SELL":
            sell_xrp += amt
            sell_cap += cap
        if cap < 0:
            negative += 1
    return buy_xrp, sell_xrp, buy_cap + sell_cap, negative


def _window_label(fills: Sequence[dict[str, str]]) -> str:
    if not fills:
        return "No fills since engine start"
    start = (fills[0].get("timestamp_utc") or "")[:19].replace("T", " ")
    end = (fills[-1].get("timestamp_utc") or "")[:19].replace("T", " ")
    if start and end:
        return f"{start} → {end} UTC"
    return "Current engine session"


def _xrp_share_pct(
    balance_xrp: float,
    balance_rlusd: float,
    mid_price: float,
) -> float:
    if mid_price <= 0:
        return 0.0
    total = balance_xrp + balance_rlusd / mid_price
    if total <= 0:
        return 0.0
    return balance_xrp / total * 100.0


def build_session_insights(
    runtime: Mapping[str, Any],
    *,
    logs_dir: str | Path = "logs",
    target_xrp_ratio: float = 0.55,
    toxic_refresh_limit: float = 0.22,
) -> SessionInsights:
    """Combine engine runtime snapshot with trades CSV since last engine start."""
    logs_path = Path(logs_dir)
    all_rows = _load_trade_rows(logs_path)
    session_rows = all_rows[_last_engine_start_index(all_rows) :]
    fills = _fill_rows(session_rows)

    buy_xrp, sell_xrp, capture_xrp, negative_count = _volume_and_capture(fills)
    n = len(fills)
    capture_per = capture_xrp / n if n else 0.0
    net_xrp = buy_xrp - sell_xrp

    mid = float(runtime.get("mid_price") or 0)
    xrp = float(runtime.get("balance_xrp") or 0)
    rlusd = float(runtime.get("balance_rlusd") or 0)
    xrp_pct = _xrp_share_pct(xrp, rlusd, mid)
    target_pct = float(target_xrp_ratio) * 100.0
    dev_pct = xrp_pct - target_pct

    toxic = float(runtime.get("toxic_fill_ratio") or 0)
    toxic_30 = float(runtime.get("toxic_fill_ratio_30s") or 0)
    cancel_per_fill = float(runtime.get("cancel_per_fill") or 0)
    engine_fills = int(runtime.get("fills_session") or 0)
    dynamic_edge = bool(runtime.get("dynamic_min_edge_enabled", False))
    book_spread = float(runtime.get("book_spread_pct") or 0)
    market_edge_met = bool(runtime.get("market_edge_met", True))
    pause_bids = bool(runtime.get("pause_bids", False))
    last_exec = str(runtime.get("last_execution_summary") or "")
    policy = str(runtime.get("quoting_policy_label") or "")

    suggestions: list[str] = []
    notes: list[str] = []

    if n != engine_fills and engine_fills > 0:
        notes.append(
            f"Engine fill tracker: {engine_fills} · CSV since restart: {n}"
        )

    if toxic >= toxic_refresh_limit or "Refresh paused" in last_exec:
        suggestions.append(
            f"Toxicity {toxic:.0%} ≥ refresh limit {toxic_refresh_limit:.0%} — "
            "wait for rolling window to clear or restart engine after reviewing fills."
        )
    elif toxic >= 0.18:
        suggestions.append(
            f"Toxicity {toxic:.0%} elevated — expect off-book / paused bids until markouts improve."
        )

    if not dynamic_edge and book_spread > 0 and book_spread < 0.12:
        suggestions.append(
            f"Book spread {book_spread:.3f}% with dynamic edge OFF — enable "
            "Dynamic min edge so quotes can compete on tight books."
        )

    if not market_edge_met:
        suggestions.append(
            "Market edge not met — quotes are wider than the book pays; fewer fills expected."
        )

    if cancel_per_fill > 2.0 and n >= 2:
        suggestions.append(
            f"Cancel/fill {cancel_per_fill:.1f} is high — reduce L1 size or wait for toxic pause to end."
        )

    if dev_pct > 6.0 and pause_bids:
        suggestions.append(
            f"XRP {xrp_pct:.0f}% vs target {target_pct:.0f}% — bids paused; "
            "unload via asks or optional manual RLUSD swap."
        )
    elif dev_pct > 8.0:
        suggestions.append(
            f"Inventory {dev_pct:+.0f} pts vs target — consider manual trim before tightening spreads."
        )

    if n >= 10 and capture_per < 0.005:
        suggestions.append(
            f"{n} fills but only {capture_xrp:+.4f} XRP capture — churn may exceed edge; widen or slow refresh."
        )

    if toxic_30 >= 0.5 and n <= 4:
        notes.append(
            f"Toxic @30s {toxic_30:.0%} on {n} fill(s) — small sample; trust Toxic ratio more."
        )

    if policy:
        notes.append(policy)

    status = "ok"
    if toxic >= toxic_refresh_limit or "Refresh paused" in last_exec:
        status = "defensive"
    elif toxic >= 0.18 or cancel_per_fill > 2.0 or (not market_edge_met and n > 0):
        status = "cautious"

    if status == "defensive":
        headline = "Defensive — refresh or touch limited"
    elif status == "cautious":
        headline = "Cautious — edge or toxicity stressed"
    elif n == 0:
        headline = "No fills yet this session"
    elif capture_xrp >= 0:
        headline = f"Spread capture {capture_xrp:+.4f} XRP on {n} fill(s)"
    else:
        headline = f"Spread capture {capture_xrp:+.4f} XRP on {n} fill(s)"

    return SessionInsights(
        status=status,
        headline=headline,
        window_label=_window_label(fills),
        fill_count=n,
        buy_count=sum(1 for f in fills if (f.get("side") or "").upper() == "BUY"),
        sell_count=sum(1 for f in fills if (f.get("side") or "").upper() == "SELL"),
        buy_xrp=buy_xrp,
        sell_xrp=sell_xrp,
        net_xrp=net_xrp,
        capture_xrp=capture_xrp,
        negative_capture_count=negative_count,
        capture_per_fill_xrp=capture_per,
        xrp_share_pct=xrp_pct,
        target_xrp_share_pct=target_pct,
        inventory_deviation_pct=dev_pct,
        engine_fills=engine_fills,
        suggestions=tuple(suggestions),
        notes=tuple(notes),
    )
