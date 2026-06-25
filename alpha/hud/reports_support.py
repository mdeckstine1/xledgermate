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
) -> str:
    logs = _logs_dir(logs_dir)
    gen = _GENERATORS.get(report_id)
    if gen is None:
        raise KeyError(f"Unknown report id: {report_id}")
    try:
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
