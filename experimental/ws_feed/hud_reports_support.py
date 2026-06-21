"""HUD Reports tab — soak-safe offline report catalog and generators."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LOGS_DEFAULT = Path("logs")

# Optional Grok config passed from HUD when generating narrative reports.
GrokConfig = Dict[str, Any]


@dataclass(frozen=True)
class ReportSpec:
    """Operator-facing report metadata for the HUD Reports tab."""

    id: str
    title: str
    subtitle: str
    category: str
    description: str
    soak_safe: bool
    engine_restart: bool
    cli_command: str
    phase_ref: str = ""


ReportGenerator = Callable[[Path], str]


def _logs_dir(logs_dir: Optional[Path] = None) -> Path:
    return logs_dir or LOGS_DEFAULT


def _gen_hourly_telegram(logs: Path) -> str:
    from scripts.hourly_telegram_report import build_report

    return build_report(window_hours=1.0, hud_url="", logs_dir=logs)


def _gen_ws_session_e15(logs: Path) -> str:
    from scripts.ws_path_session_report import build_e15_report, format_e15_report

    repo = logs.parent if logs.name == "logs" else logs
    return format_e15_report(build_e15_report(repo=repo))


def _gen_fill_quote_age(logs: Path) -> str:
    from scripts.fill_quote_age_report import build_fill_age_report, format_fill_age_report

    return format_fill_age_report(build_fill_age_report(logs_dir=logs))


def _gen_acquisition_metrics(logs: Path) -> str:
    from scripts.acquisition_metrics_report import (
        build_acquisition_report,
        format_acquisition_report_cli,
    )

    return format_acquisition_report_cli(build_acquisition_report(logs_dir=logs))


def _gen_ws_runtime_analysis(logs: Path) -> str:
    from experimental.ws_runtime_analysis import (
        collect_samples,
        format_runtime_analysis_report,
        run_runtime_analysis,
    )

    primary = logs / "runtime_state.json"
    if primary.exists():
        analysis = run_runtime_analysis(path=primary, logs_dir=logs)
        label = "logs/runtime_state.json"
        if analysis.sample_count == 0:
            samples, _ = collect_samples(primary=primary, logs_dir=logs)
            if samples:
                from experimental.ws_runtime_analysis import analyze_samples

                analysis = analyze_samples(samples)
                analysis.source_notes = [f"{label}: snapshot (no sample_history yet)"]
        return format_runtime_analysis_report(analysis, path_label=label)

    demo = logs / "ws_as_demo_runtime.json"
    if demo.exists():
        analysis = run_runtime_analysis(path=demo, logs_dir=logs)
        return format_runtime_analysis_report(analysis, path_label=str(demo))

    return (
        "=== WS runtime analysis ===\n\n"
        "No logs/runtime_state.json or logs/ws_as_demo_runtime.json found.\n"
        "Start ws-engine or live_pure_as_tester to populate runtime export."
    )


def _gen_g6_activation(logs: Path) -> str:
    from experimental.ws_feed.live_activation_grading import build_g6_report, format_g6_report

    return format_g6_report(
        build_g6_report(runtime_path=logs / "runtime_state.json", logs_dir=logs)
    )


def _gen_hourly_soak_trend(logs: Path) -> str:
    from scripts.hourly_soak_trend import format_hourly_soak_trend

    return format_hourly_soak_trend(logs_dir=logs)


def _gen_grok_suggestions(logs: Path) -> str:
    from scripts.grok_suggestions_report import (
        build_grok_suggestions_report,
        format_grok_suggestions_report,
    )

    return format_grok_suggestions_report(build_grok_suggestions_report(logs_dir=logs))


def _gen_clob_amm_monitor(logs: Path) -> str:
    from experimental.arb.clob_amm_monitor import format_clob_amm_report

    return format_clob_amm_report(logs_dir=logs)


def _gen_qd_layered_decision(logs: Path) -> str:
    from scripts.qd_layered_report import build_qd_layered_report, format_qd_layered_report

    return format_qd_layered_report(build_qd_layered_report(logs_dir=logs))


def _gen_qd_final_diagnostics(logs: Path) -> str:
    from scripts.qd_final_report import build_qd_final_report, format_qd_final_report

    return format_qd_final_report(build_qd_final_report(logs_dir=logs))


def _gen_soak_dashboard(logs: Path, *, narrative: bool = False, grok_config: Optional[GrokConfig] = None) -> str:
    from scripts.soak_dashboard_report import build_soak_dashboard_report

    cfg = grok_config or {}
    return build_soak_dashboard_report(
        logs_dir=logs,
        narrative=narrative,
        grok_key=str(cfg.get("intel_ai_key") or ""),
        grok_model=str(cfg.get("intel_ai_model") or "grok-3"),
        grok_enabled=bool(cfg.get("grok_enabled", True)),
    )


def _gen_reservation_snapshot(logs: Path) -> str:
    from experimental.ws_feed.reservation_metrics import (
        enrich_runtime_reservation_metrics,
        format_reservation_bbo_delta,
    )
    from scripts.qd_report_common import fmt_on_off, operating_mode, side_permission_block

    path = logs / "runtime_state.json"
    if not path.exists():
        return "No logs/runtime_state.json — start ws-engine or wait for first cycle."
    try:
        rs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "Could not read runtime_state.json"

    rs = enrich_runtime_reservation_metrics(rs)
    hud: dict = {}
    try:
        from experimental.ws_feed.qd_hud import build_qd_hud_fields

        hud = build_qd_hud_fields(rs)
    except Exception:
        hud = {}
    snap = hud.get("qd_snapshot") or {}
    bid = snap.get("bid") or {}

    mode_label, mode_hint = operating_mode(
        intent=str(rs.get("qd_intent") or snap.get("intent") or ""),
        book_mode=str(rs.get("qd_book_mode") or snap.get("book_mode") or ""),
        solo_mode=bool(rs.get("solo_mode", snap.get("solo_mode"))),
        bid_allowed=rs.get("qd_bid_allowed", bid.get("allowed")),
        ask_allowed=rs.get("qd_ask_allowed"),
        protection_active=bool(rs.get("qd_bid_bleeding") or rs.get("qd_ask_bleeding")),
        would_quote=rs.get("qd_would_quote"),
    )

    delta = rs.get("reservation_to_bbo_delta_bps")
    inside = rs.get("inside_l1")
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  RESERVATION → QUOTE PATH (L5 permissions + A-S reservation)  ║",
        "╚══════════════════════════════════════════════════════════════╝",
        f"generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"cycle: {rs.get('cycle_count')} | ws: {rs.get('ws_as_version') or '—'}",
        "",
        "▶ OPERATING MODE",
        f"  {mode_label}",
        f"  {mode_hint}",
        "",
        "L2 · INTENT",
        f"  qd_intent: {rs.get('qd_intent') or snap.get('intent') or '—'}",
        f"  reason: {rs.get('qd_intent_reason') or snap.get('intent_reason') or '—'}",
        f"  book: {rs.get('qd_book_mode') or '—'} | solo: {rs.get('solo_mode')} | drift: {rs.get('qd_drift_band') or '—'}",
        "",
        "L5 · PERMISSIONS → QUOTE",
    ]
    lines.extend(side_permission_block(
        "bid",
        allowed=rs.get("qd_bid_allowed"),
        pause_cause=str(rs.get("qd_bid_pause_cause") or ""),
        block_reason=str(rs.get("qd_bid_block_reason") or ""),
        edge_viable=rs.get("qd_bid_edge_viable"),
        edge_bps=rs.get("qd_bid_implied_bps"),
        bleeding=rs.get("qd_bid_bleeding"),
    ))
    lines.append("")
    lines.extend(side_permission_block(
        "ask",
        allowed=rs.get("qd_ask_allowed"),
        pause_cause=str(rs.get("qd_ask_pause_cause") or ""),
        block_reason=str(rs.get("qd_ask_block_reason") or ""),
        edge_viable=rs.get("qd_ask_edge_viable"),
        edge_bps=rs.get("qd_ask_implied_bps"),
        bleeding=rs.get("qd_ask_bleeding"),
    ))
    lines.extend([
        "",
        "INVENTORY CB",
        f"  mode: {rs.get('qd_inventory_cb_mode') or '—'}",
        f"  note: {rs.get('qd_inventory_cb_note') or '—'}",
        "",
        "RESERVATION vs BBO",
        f"  mid: {rs.get('mid_price')}",
        f"  best_bid / best_ask: {rs.get('best_bid_rlusd_per_xrp')} / {rs.get('best_ask_rlusd_per_xrp')}",
        f"  as_reservation: {rs.get('as_reservation')}",
        f"  Res→BBO: {format_reservation_bbo_delta(delta, inside_l1=inside)}",
        f"  inside_l1: {inside}",
        "",
        "OUTCOME",
        f"  qd_would_quote: {fmt_on_off(rs.get('qd_would_quote'))}",
        f"  zero_quote_reason: {rs.get('zero_quote_reason') or rs.get('edge_resolution_summary') or '—'}",
        f"  open_offers: {rs.get('open_offers_count') or len(rs.get('open_offers') or [])}",
        f"  as_presence_pct: {rs.get('as_presence_pct')}",
        "",
        "Soak-safe · runtime_state.json · Full stack: Reports → Layered quote decision",
    ])
    return "\n".join(lines)


REPORT_SPECS: List[ReportSpec] = [
    ReportSpec(
        id="qd_layered_decision",
        title="QD stack overview",
        subtitle="Operating mode + L1–L5 (primary monitor)",
        category="Quote Decision",
        description=(
            "Start here. Shows ACCUMULATING / TRIM / QUOTING mode, posture, intent, edge gate, "
            "bleed, L5 qd_bid/ask_allowed, inventory CB, and recent accumulate vs trim mix."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/qd_layered_report.py",
        phase_ref="QD L1–L5",
    ),
    ReportSpec(
        id="qd_final_diagnostics",
        title="L5 permission monitor",
        subtitle="Per-cycle permissions + QD_FINAL tail",
        category="Quote Decision",
        description=(
            "Live L5 monitor: bid/ask allowed, block causes (edge/intent/bleed/inventory/tape), "
            "edge bps, inventory_cb_skipped_solo, and recent QD_FINAL cycle log."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/qd_final_report.py",
        phase_ref="QD L5",
    ),
    ReportSpec(
        id="hourly_telegram",
        title="Hourly operator summary",
        subtitle="Telegram preview (last 1h)",
        category="Operator",
        description="Same text as the hourly Telegram cron — fills, capture, portfolio, layered QD posture/intent/L5, Res→BBO when WS pure.",
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/hourly_telegram_report.py --dry-run",
        phase_ref="Ops / Telegram",
    ),
    ReportSpec(
        id="reservation_snapshot",
        title="Reservation → quote path",
        subtitle="L5 permissions flowing into A-S reservation",
        category="Quote Decision",
        description=(
            "How L5 qd_bid/ask_allowed and intent connect to reservation vs BBO and actual "
            "would_quote / open offers. Quick check when permissions say ON but no quotes appear."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="(HUD report only)",
        phase_ref="QD + A-S",
    ),
    ReportSpec(
        id="ws_session_e15",
        title="E1.5 WS session gate",
        subtitle="Legacy soak gate — fills + markout",
        category="Archive",
        description=(
            "Pre-layered soak milestone gate (50+ fills, toxicity, markout). Still useful for "
            "long-run session review; not part of live QD decision path."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/ws_path_session_report.py",
        phase_ref="Archive · E1.5",
    ),
    ReportSpec(
        id="g6_activation",
        title="G6 activation grade",
        subtitle="Legacy soak gate — pilot tier",
        category="Archive",
        description=(
            "Pre-layered activation tier (pilot → active). Portfolio/fill grading still useful "
            "for soak milestones; orthogonal to L5 qd_bid/ask_allowed."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python -m experimental.ws_feed.live_activation_grading",
        phase_ref="Archive · G6",
    ),
    ReportSpec(
        id="fill_quote_age",
        title="Fill quote age (offline)",
        subtitle="M2 prep — trades + OFFER_REFRESH",
        category="Soak analysis",
        description="Approximate resting-quote age at detected fill. Lower bound when offers are kept without refresh.",
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/fill_quote_age_report.py",
        phase_ref="Phase M2 prep",
    ),
    ReportSpec(
        id="acquisition_metrics",
        title="Acquisition metrics",
        subtitle="Edge-positive inventory vs spot",
        category="Soak analysis",
        description=(
            "Session BUY efficiency, solo accumulate cycle rate (QD L2), capture by inventory "
            "state from fill_quote_age + intel JSONL."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/acquisition_metrics_report.py",
        phase_ref="Acquisition soak",
    ),
    ReportSpec(
        id="ws_runtime_analysis",
        title="WS runtime analysis",
        subtitle="Presence, flips, zero_quote breakdown",
        category="Soak analysis",
        description="C1/C2 metrics from runtime export. Full time series needs production sample_history (M4).",
        soak_safe=True,
        engine_restart=False,
        cli_command="python -m experimental.ws_runtime_analysis --path logs/runtime_state.json",
        phase_ref="Phase A2/C1",
    ),
    ReportSpec(
        id="hourly_soak_trend",
        title="Hourly soak trend",
        subtitle="Last 24h UTC buckets",
        category="Soak analysis",
        description="Per-hour fills, capture, toxicity, markout, book age from trades CSV + intel_decisions.jsonl.",
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/hourly_soak_trend.py",
        phase_ref="Soak ops",
    ),
    ReportSpec(
        id="grok_suggestions",
        title="Grok suggestions",
        subtitle="Analyze_competitor log tail",
        category="Intelligence",
        description="Recent grok_suggestion rows from intel_decisions.jsonl (F4 outcome tracking prep).",
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/grok_suggestions_report.py",
        phase_ref="Phase F4",
    ),
    ReportSpec(
        id="clob_amm_monitor",
        title="CLOB vs AMM monitor",
        subtitle="H1 read-only dislocation log",
        category="Phase H",
        description="Tail logs/clob_amm_spread.jsonl — CLOB mid vs AMM implied price; no trades.",
        soak_safe=True,
        engine_restart=False,
        cli_command="(ws-hud polls ~60s; report view only)",
        phase_ref="Phase H1",
    ),
    ReportSpec(
        id="soak_dashboard",
        title="Soak dashboard",
        subtitle="Operator summary + technical appendix",
        category="Soak analysis",
        description=(
            "Sections 1–3: runtime, layered QD decision state (L5/edge/bleed), soak metrics. "
            "Appendix: C2/G6 gates, hourly trend, fill age detail. No Grok."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/soak_dashboard_report.py",
        phase_ref="Soak ops",
    ),
    ReportSpec(
        id="soak_dashboard_narrative",
        title="Soak dashboard + narrative",
        subtitle="Operator summary + Grok advisory",
        category="Soak analysis",
        description=(
            "Same operator layout as Soak dashboard: runtime, QD intent/L5 permissions, soak health, "
            "then Grok narrative on accumulate vs trim and gate status. Requires Grok key."
        ),
        soak_safe=True,
        engine_restart=False,
        cli_command="python scripts/soak_dashboard_report.py --narrative",
        phase_ref="Soak ops / F4",
    ),
]

_GENERATORS: Dict[str, ReportGenerator] = {
    "qd_layered_decision": _gen_qd_layered_decision,
    "hourly_telegram": _gen_hourly_telegram,
    "reservation_snapshot": _gen_reservation_snapshot,
    "qd_final_diagnostics": _gen_qd_final_diagnostics,
    "ws_session_e15": _gen_ws_session_e15,
    "g6_activation": _gen_g6_activation,
    "fill_quote_age": _gen_fill_quote_age,
    "acquisition_metrics": _gen_acquisition_metrics,
    "ws_runtime_analysis": _gen_ws_runtime_analysis,
    "hourly_soak_trend": _gen_hourly_soak_trend,
    "grok_suggestions": _gen_grok_suggestions,
    "clob_amm_monitor": _gen_clob_amm_monitor,
    "soak_dashboard": _gen_soak_dashboard,
    "soak_dashboard_narrative": lambda logs: _gen_soak_dashboard(logs, narrative=True),
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
    grok_config: Optional[GrokConfig] = None,
) -> str:
    logs = _logs_dir(logs_dir)
    if report_id == "soak_dashboard":
        return _gen_soak_dashboard(logs, narrative=False, grok_config=grok_config)
    if report_id == "soak_dashboard_narrative":
        return _gen_soak_dashboard(logs, narrative=True, grok_config=grok_config)
    gen = _GENERATORS.get(report_id)
    if gen is None:
        raise KeyError(f"Unknown report id: {report_id}")
    try:
        return gen(logs)
    except Exception as exc:
        return (
            f"=== Report error: {report_id} ===\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            "Check logs/ exists and ws-engine has written runtime_state.json."
        )


def report_view_url(report_id: str) -> str:
    return f"/report/{report_id}"


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
            badges.append('<span class="badge soak">Soak-safe</span>')
        if not spec.engine_restart:
            badges.append('<span class="badge ok">No ws-engine restart</span>')
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
  <title>{html.escape(title)} — XLedgerMate</title>
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
