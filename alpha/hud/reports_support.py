"""Alpha HUD Reports tab — read-only catalog and generators."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LOGS_DEFAULT = Path("logs")

ReportGenerator = Callable[[Path], str]


@dataclass(frozen=True)
class ReportSpec:
    id: str
    title: str
    subtitle: str
    category: str
    description: str
    soak_safe: bool
    engine_restart: bool
    cli_command: str
    phase_ref: str = ""


def _logs_dir(logs_dir: Optional[Path] = None) -> Path:
    return logs_dir or LOGS_DEFAULT


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _gen_alpha_cycle(logs: Path) -> str:
    state = _load_json(logs / "alpha_runtime_state.json")
    text = str(state.get("report_text") or "").strip()
    if text:
        return text
    return (
        "=== Alpha cycle report ===\n\n"
        "No report_text in logs/alpha_runtime_state.json yet.\n"
        "Wait for the next engine cycle or run: python -m alpha status"
    )


def _gen_alpha_hourly(logs: Path) -> str:
    from scripts.hourly_telegram_report import build_alpha_report

    return build_alpha_report(window_hours=1.0, logs_dir=logs)


def _gen_alpha_hourly_24h(logs: Path) -> str:
    from scripts.hourly_telegram_report import build_alpha_report

    return build_alpha_report(window_hours=24.0, logs_dir=logs)


def _gen_alpha_realized_pnl(logs: Path) -> str:
    from alpha.reporting.realized_pnl import (
        build_realized_pnl_snapshot,
        format_realized_pnl_context_block,
    )

    state = _load_json(logs / "alpha_runtime_state.json")
    risk = state.get("risk") or {}
    snap = build_realized_pnl_snapshot(
        logs_dir=logs,
        hours=24.0,
        session_pnl_xrp=risk.get("session_pnl_xrp"),
        mid_rlusd_per_xrp=state.get("mid"),
    )
    block = format_realized_pnl_context_block(snap)
    recent = snap.get("recent_exits") or []
    if recent:
        block += "\n\nRecent exits:"
        for row in recent:
            block += (
                f"\n  {row.get('ts', '')[:19]} {row.get('kind')} "
                f"xrp={row.get('xrp')} profit={row.get('profit_xrp_equiv')} "
                f"{row.get('notes', '')}"
            )
    if snap.get("interpretation"):
        block += f"\n\nInterpretation: {snap['interpretation']}"
    return block


def _gen_alpha_ohlc_ta(logs: Path) -> str:
    from alpha.decision.ohlc_cache import cache_status
    from alpha.decision.ta_config import effective_ta_candle_interval_seconds
    from config.settings import BotConfig
    from alpha.operator.runtime import apply_overrides, OperatorRuntimeStore

    base = BotConfig.load()
    overrides = OperatorRuntimeStore(overrides_path=logs / "alpha_overrides.json").load_overrides()
    effective = apply_overrides(base, overrides)
    ta_cfg = effective.alpha_technical_analysis
    interval = effective_ta_candle_interval_seconds(
        ta_cfg,
        cycle_seconds=effective.alpha_cycle_interval_seconds,
        sample_interval_seconds=effective.alpha_price_sample_interval_seconds,
    )
    status = cache_status(logs, ta_interval_seconds=interval)
    lines = [
        "=== OHLC cache & TA warmup ===",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"db_present: {status.get('db_present')}",
        f"ta_interval_seconds: {status.get('ta_interval_seconds')}",
        f"closed_bars: {status.get('closed_bars')} / cap {status.get('bars_cap')}",
        f"last_tick_utc: {status.get('last_tick_utc')}",
        f"gap_seconds: {status.get('gap_seconds')}",
        f"rebuilt_from_ticks: {status.get('rebuilt_from_ticks')}",
        "",
        "Indicator warmup (closed bars at active TF):",
    ]
    warmup = status.get("indicator_warmup") or {}
    for row in warmup.get("indicators") or []:
        flag = "ready" if row.get("ready") else "warming"
        lines.append(
            f"  {row.get('name')}: {row.get('have')}/{row.get('need')} ({flag})"
        )
    intervals = status.get("intervals") or {}
    if intervals:
        lines.append("\nCached intervals:")
        for key, meta in sorted(intervals.items(), key=lambda kv: int(kv[0])):
            lines.append(
                f"  {key}s: closed={meta.get('closed_bars')} total={meta.get('total_bars')}"
            )
    ta = _load_json(logs / "alpha_runtime_state.json").get("technical_analysis") or {}
    if ta:
        lines.extend(
            [
                "",
                "Latest TA snapshot:",
                f"  summary: {ta.get('summary', '')}",
                f"  buy_score={ta.get('buy_score')} sell_score={ta.get('sell_score')}",
                f"  rsi={ta.get('rsi')} stoch_k={ta.get('stoch_k')}",
            ]
        )
    return "\n".join(lines)


def _gen_alpha_brackets(logs: Path) -> str:
    from alpha.orders.state import BracketStateStore
    from alpha.reporting.service import bracket_summary_from_store

    store = BracketStateStore(persist_path=logs / "alpha_brackets.json")
    summary = bracket_summary_from_store(store)
    lines = [
        "=== Bracket store summary ===",
        f"total={summary.total} pending_buys={summary.pending_buys}",
        f"active_fixed={summary.active_fixed} sl_trailing={summary.active_sl_trailing}",
        f"breakout_trailing={summary.active_breakout_trailing}",
        "",
        "Active / pending (last 40):",
    ]
    shown = 0
    skip_states = {"tp_filled", "sl_filled", "cancelled"}
    for record in store.all_records():
        if record.state.value in skip_states:
            continue
        shown += 1
        if shown > 40:
            lines.append("  … truncated")
            break
        lines.append(
            f"  {record.bracket_id[:12]} state={record.state.value} "
            f"entry={record.entry_price_rlusd_per_xrp} xrp={record.filled_xrp or record.target_size_xrp} "
            f"tp={record.tp_leg.price_rlusd_per_xrp if record.tp_leg else '—'} "
            f"sl={record.sl_leg.price_rlusd_per_xrp if record.sl_leg else '—'}"
        )
    if shown == 0:
        lines.append("  (no open brackets)")
    return "\n".join(lines)


def _gen_alpha_activity(logs: Path) -> str:
    path = logs / "alpha_activity.jsonl"
    if not path.is_file():
        return "No logs/alpha_activity.jsonl yet."
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return f"Could not read activity log: {exc}"
    tail = [ln for ln in lines if ln.strip()][-80:]
    out = ["=== Recent activity (last 80 events) ===", ""]
    out.extend(tail or ["(empty)"])
    return "\n".join(out)


def _gen_alpha_reentry(logs: Path) -> str:
    data = _load_json(logs / "alpha_reentry.json")
    if not data:
        return "No logs/alpha_reentry.json — reentry gate not persisted yet."
    return "=== Re-entry gate state ===\n\n" + json.dumps(data, indent=2)


def _gen_alpha_market_metrics(logs: Path) -> str:
    from alpha.decision.market_metrics import format_metrics_report

    return format_metrics_report(logs, hours=24.0)


def _current_trades_path(logs: Path) -> Path:
    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
    return logs / f"trades_{month}.csv"


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    import csv

    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _format_csv_table(rows: List[Dict[str, str]], *, columns: List[str]) -> List[str]:
    if not rows:
        return ["(no rows)"]
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            widths[col] = max(widths[col], len(str(row.get(col, ""))))
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    sep = "  ".join("-" * widths[col] for col in columns)
    lines = [header, sep]
    for row in rows:
        lines.append("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))
    return lines


def _summarize_trades_rows(rows: List[Dict[str, str]]) -> List[str]:
    buys = sells = transfers = taxable = 0
    profit = 0.0
    for row in rows:
        et = (row.get("event_type") or "").upper()
        if et == "BUY":
            buys += 1
        elif et == "SELL":
            sells += 1
        elif et == "TRANSFER":
            transfers += 1
        if (row.get("taxable") or "").upper() == "Y":
            taxable += 1
        try:
            profit += float(row.get("profit_xrp_equiv") or 0)
        except (TypeError, ValueError):
            pass
    return [
        f"rows={len(rows)} taxable={taxable} buys={buys} sells={sells} transfers={transfers}",
        f"sum_profit_xrp_equiv={profit:.6f}",
    ]


def _gen_alpha_trades_csv(logs: Path) -> str:
    from alpha.reporting.tax_ledger import format_monthly_report
    from datetime import datetime, timezone

    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
    return format_monthly_report(logs, month)


def _gen_alpha_trades_month(logs: Path, *, month: str) -> str:
    from alpha.reporting.tax_ledger import format_monthly_report

    return format_monthly_report(logs, month)


def _gen_alpha_tax_year(logs: Path, *, year: int) -> str:
    from alpha.reporting.tax_ledger import format_yearly_report

    return format_yearly_report(logs, year)


def _gen_alpha_transfers(logs: Path) -> str:
    path = logs / "transfers.csv"
    rows = _read_csv_rows(path)
    lines = [
        "=== Outbound transfers log ===",
        "path: logs/transfers.csv",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "HUD Config → Send payments append here. Taxable TRANSFER rows also land in",
        f"the monthly trades file ({_current_trades_path(logs).name}).",
        "",
    ]
    if not path.is_file():
        lines.append("File not found — no withdrawals via HUD Send yet.")
        return "\n".join(lines)
    lines.append(f"rows={len(rows)}")
    lines.append("")
    cols = ["timestamp_utc", "network", "asset", "amount", "destination", "tx_hash"]
    lines.extend(_format_csv_table(rows[-100:], columns=cols))
    return "\n".join(lines)


def _gen_alpha_trades_archive(logs: Path) -> str:
    paths = sorted(logs.glob("trades_*.csv"), key=lambda p: p.name)
    lines = [
        "=== Trades / tax CSV archive ===",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
    ]
    if not paths:
        lines.append("No logs/trades_*.csv files found.")
        return "\n".join(lines)
    for path in paths:
        rows = _read_csv_rows(path)
        summary = _summarize_trades_rows(rows) if rows else ["rows=0"]
        lines.append(f"{path.name}: " + " | ".join(summary))
    current = _current_trades_path(logs)
    lines.extend(["", f"Current month detail: open report alpha_trades_csv ({current.name})", ""])
    for path in paths[-6:]:
        rows = _read_csv_rows(path)
        if not rows:
            continue
        lines.extend([f"--- {path.name} (last 15) ---", ""])
        cols = ["timestamp_utc", "event_type", "side", "xrp_amount", "profit_xrp_equiv", "notes"]
        lines.extend(_format_csv_table(rows[-15:], columns=cols))
        lines.append("")
    return "\n".join(lines).rstrip()


REPORT_SPECS: List[ReportSpec] = [
    ReportSpec(
        id="alpha_cycle",
        title="Latest cycle report",
        subtitle="Same text as Telegram / Reports pre",
        category="Operator",
        description="Full cycle snapshot: portfolio, inventory, risk, decision, brackets.",
        soak_safe=True,
        engine_restart=False,
        cli_command="python -m alpha status --no-telegram",
        phase_ref="Alpha ops",
    ),
    ReportSpec(
        id="alpha_hourly",
        title="Hourly operator summary",
        subtitle="Last 1 hour",
        category="Operator",
        description="Telegram hourly digest preview for Alpha.",
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/hourly_telegram_report.py --dry-run",
        phase_ref="Telegram",
    ),
    ReportSpec(
        id="alpha_hourly_24h",
        title="24h operator summary",
        subtitle="Rolling 24-hour window",
        category="Operator",
        description="Extended hourly digest — cycles and posture over 24h.",
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/hourly_telegram_report.py --dry-run",
        phase_ref="Telegram",
    ),
    ReportSpec(
        id="alpha_realized_pnl",
        title="Realized bracket P&L",
        subtitle="Tax CSV exits (24h)",
        category="P&L",
        description="TP/SL realized profit from logs/trades_*.csv — not session MTM.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report only)",
        phase_ref="Tax / P&L",
    ),
    ReportSpec(
        id="alpha_ohlc_ta",
        title="OHLC cache & TA warmup",
        subtitle="SQLite bars + indicator readiness",
        category="Technical analysis",
        description="OHLC DB health, gap seconds, closed bars per TF, RSI/Stoch/BB warmup.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report only)",
        phase_ref="TA / OHLC",
    ),
    ReportSpec(
        id="alpha_brackets",
        title="Bracket store",
        subtitle="Open brackets and modes",
        category="Orders",
        description="Pending buys, active TP/SL/trailing brackets from alpha_brackets.json.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report only)",
        phase_ref="Brackets",
    ),
    ReportSpec(
        id="alpha_activity",
        title="Activity log tail",
        subtitle="Last 80 JSONL events",
        category="Operator",
        description="Recent cycles, config reloads, cancel_all from alpha_activity.jsonl.",
        soak_safe=True,
        engine_restart=False,
        cli_command="tail -80 logs/alpha_activity.jsonl",
        phase_ref="Audit",
    ),
    ReportSpec(
        id="alpha_reentry",
        title="Re-entry gate state",
        subtitle="Post-TP / post-SL cooldowns",
        category="Orders",
        description="Persisted reentry gate — cycles remaining, stabilization flags.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report only)",
        phase_ref="Re-entry",
    ),
    ReportSpec(
        id="alpha_market_metrics",
        title="Market metrics (vol & liquidity)",
        subtitle="ATR, realized vol, spread, depth, regime",
        category="Market",
        description="Per-cycle SQLite metrics — 24h averages and latest regime tag.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report only)",
        phase_ref="TA",
    ),
    ReportSpec(
        id="alpha_trades_csv",
        title="Monthly trades / tax log",
        subtitle="Current month (logs/trades_YYYY-MM.csv)",
        category="Tax & transfers",
        description="BUY/SELL bracket fills and taxable TRANSFER rows for the current calendar month.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report · logs/trades_YYYY-MM.csv)",
        phase_ref="Tax CSV",
    ),
    ReportSpec(
        id="alpha_trades_month",
        title="Monthly trades / tax log (select month)",
        subtitle="?month=YYYY-MM on report URL",
        category="Tax & transfers",
        description="Full monthly tax CSV view — use Reports tab month dropdown or ?month=YYYY-MM.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report · ?month=YYYY-MM)",
        phase_ref="Tax CSV",
    ),
    ReportSpec(
        id="alpha_tax_year",
        title="Annual tax rollup",
        subtitle="Year totals + logs/tax/trades_YYYY_annual.csv",
        category="Tax & transfers",
        description="Merges all monthly files for a calendar year; writes yearly CSV for export.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report · ?year=YYYY)",
        phase_ref="Tax CSV",
    ),
    ReportSpec(
        id="alpha_transfers",
        title="Transfers log",
        subtitle="logs/transfers.csv",
        category="Tax & transfers",
        description="Outbound XRP/RLUSD payments from HUD Config → Send (destination + tx hash).",
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report · logs/transfers.csv)",
        phase_ref="Withdrawals",
    ),
    ReportSpec(
        id="alpha_trades_archive",
        title="Trades CSV archive",
        subtitle="All logs/trades_*.csv months",
        category="Tax & transfers",
        description="Index every monthly trades file with row counts and recent rows per month.",
        soak_safe=True,
        engine_restart=False,
        cli_command="ls -la logs/trades_*.csv",
        phase_ref="Tax CSV",
    ),
]

_GENERATORS: Dict[str, ReportGenerator] = {
    "alpha_cycle": _gen_alpha_cycle,
    "alpha_hourly": _gen_alpha_hourly,
    "alpha_hourly_24h": _gen_alpha_hourly_24h,
    "alpha_realized_pnl": _gen_alpha_realized_pnl,
    "alpha_ohlc_ta": _gen_alpha_ohlc_ta,
    "alpha_brackets": _gen_alpha_brackets,
    "alpha_activity": _gen_alpha_activity,
    "alpha_reentry": _gen_alpha_reentry,
    "alpha_market_metrics": _gen_alpha_market_metrics,
    "alpha_trades_csv": _gen_alpha_trades_csv,
    "alpha_transfers": _gen_alpha_transfers,
    "alpha_trades_archive": _gen_alpha_trades_archive,
}


def list_reports() -> List[Dict[str, Any]]:
    return [asdict(spec) for spec in REPORT_SPECS]


def get_report_spec(report_id: str) -> Optional[ReportSpec]:
    for spec in REPORT_SPECS:
        if spec.id == report_id:
            return spec
    return None


def generate_report_text(
    report_id: str,
    *,
    logs_dir: Optional[Path] = None,
    month: Optional[str] = None,
    year: Optional[int] = None,
) -> str:
    logs = _logs_dir(logs_dir)
    try:
        if report_id == "alpha_trades_month":
            from datetime import datetime, timezone

            key = month or datetime.now(tz=timezone.utc).strftime("%Y-%m")
            return _gen_alpha_trades_month(logs, month=key)
        if report_id == "alpha_tax_year":
            from datetime import datetime, timezone

            y = int(year if year is not None else datetime.now(tz=timezone.utc).year)
            return _gen_alpha_tax_year(logs, year=y)
        gen = _GENERATORS.get(report_id)
        if gen is None:
            raise KeyError(f"Unknown report id: {report_id}")
        return gen(logs)
    except Exception as exc:
        return (
            f"=== Report error: {report_id} ===\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            "Check logs/ and that xledgermate-alpha has run at least one cycle."
        )


def wrap_report_html(
    *,
    report_id: str,
    title: str,
    subtitle: str,
    body_text: str,
    spec: Optional[ReportSpec] = None,
) -> str:
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_body = html.escape(body_text)
    badges = []
    if spec:
        if spec.soak_safe:
            badges.append('<span class="badge soak">Read-only</span>')
        if not spec.engine_restart:
            badges.append('<span class="badge ok">No engine restart</span>')
        if spec.phase_ref:
            badges.append(f'<span class="badge ref">{html.escape(spec.phase_ref)}</span>')
    badge_html = " ".join(badges)
    cli = html.escape(spec.cli_command if spec else "")
    report_label = html.escape(f"Report ID: {report_id}")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} — Alpha HUD</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 16px 20px 32px; }}
    a {{ color: #60a5fa; }}
    .header {{ max-width: 1100px; margin: 0 auto 12px; }}
    h1 {{ margin: 0 0 4px; font-size: 1.35rem; color: #f8fafc; }}
    .sub {{ color: #94a3b8; font-size: 0.85rem; margin-bottom: 8px; }}
    .meta {{ font-size: 0.75rem; color: #64748b; margin-bottom: 10px; }}
    .badge {{ display: inline-block; font-size: 0.65rem; padding: 2px 8px; border-radius: 4px; margin-right: 6px; }}
    .badge.soak {{ background: #14532d; color: #86efac; }}
    .badge.ok {{ background: #1e3a5f; color: #93c5fd; }}
    .badge.ref {{ background: #334155; color: #cbd5e1; }}
    pre {{ max-width: 1100px; margin: 0 auto; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 14px 16px; overflow-x: auto; font-size: 0.78rem; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }}
    .cli {{ max-width: 1100px; margin: 12px auto 0; font-size: 0.72rem; color: #64748b; }}
    .actions {{ margin-top: 10px; }}
    button {{ background: #334155; color: #e2e8f0; border: none; border-radius: 4px; padding: 6px 12px; cursor: pointer; font-size: 0.8rem; margin-right: 8px; }}
    button:hover {{ background: #475569; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>{html.escape(title)}</h1>
    <div class="sub">{html.escape(subtitle)}</div>
    <div class="meta">{report_label} · Generated {generated}</div>
    <div>{badge_html}</div>
    <div class="actions">
      <button type="button" onclick="location.reload()">↻ Refresh report</button>
      <a href="/"><button type="button">← Back to HUD</button></a>
    </div>
  </div>
  <pre id="body">{safe_body}</pre>
  <div class="cli">CLI equivalent: <code>{cli}</code></div>
</body>
</html>"""
