#!/usr/bin/env python3
"""Soak dashboard — operator summary + optional Grok narrative (HUD Reports tab)."""

from __future__ import annotations

import csv
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experimental.ws_feed.live_activation_grading import build_g6_report, format_g6_report
from experimental.ws_runtime_analysis import format_runtime_analysis_report, run_runtime_analysis
from scripts.fill_quote_age_report import build_fill_age_report, format_fill_age_report
from scripts.hourly_soak_trend import format_hourly_soak_trend
from scripts.ws_path_session_report import count_ws_fills_csv

SOAK_NARRATIVE_PROMPT = """You are reviewing a live pure Avellaneda–Stoikov market maker soak on XRPL (v2.3+ layered quote decision stack).

Below is an OPERATOR SUMMARY from logs. Use ONLY these facts. Do not invent metrics.

Context:
- L1–L5 layered QD replaces legacy A2 gates. L5 sets qd_bid_allowed / qd_ask_allowed.
- Solo books: inventory_cb is often skipped; L2 intent (SOLO_ACCUMULATE_ON_EDGE vs INVENTORY_UNLOAD) drives behavior.
- Acquisition-centered MM: accumulate on good buy edges; trim when edge is thin on solo with heavy XRP drift.

Your job:
1. What phase is this soak in? (early warming, accumulating, trim-only, stable)
2. Is layered QD behavior consistent with design? (cite intent, L5 permissions, edge gate, inventory_cb)
3. Separate trading edge (spread capture, markout, toxic) from spot/MTM (portfolio)
4. Gate status (G6, C2) in plain English — insufficient samples is expected early
5. One short closing paragraph: "nothing urgent" vs "watch these 2 metrics"

Rules:
- Max 4 short paragraphs. Plain prose only — no ## headers, no JSON, no code fences.
- Do NOT recommend changing G7, tightening quotes, or overriding A-S reservation.
- Do NOT suggest mid-soak strategy overrides.
- If data is missing, say so briefly.

OPERATOR SUMMARY:
"""


def _section(title: str) -> str:
    return f"\n{'=' * 60}\n{title}\n{'=' * 60}\n"


def _load_runtime(logs: Path) -> Dict[str, Any]:
    path = logs / "runtime_state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _intel_cycle_window(logs: Path, *, tail: int = 500) -> Dict[str, Any]:
    path = logs / "intel_decisions.jsonl"
    if not path.exists():
        return {"cycles": [], "count": 0}
    cycles: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("kind") == "cycle":
            cycles.append(row)
    return {"cycles": cycles, "count": len(cycles)}


def _would_quote_window_pct(cycles: List[Dict[str, Any]]) -> Tuple[float, int, int]:
    if not cycles:
        return 0.0, 0, 0
    wq = sum(1 for c in cycles if c.get("would_quote"))
    return 100.0 * wq / len(cycles), wq, len(cycles)


def _book_age_p95(cycles: List[Dict[str, Any]], runtime: Dict[str, Any]) -> Optional[float]:
    ages: List[float] = []
    for c in cycles:
        age = c.get("ws_book_age_s")
        if age is not None:
            try:
                ages.append(float(age))
            except (TypeError, ValueError):
                pass
    if ages:
        ordered = sorted(ages)
        idx = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
        return round(ordered[idx], 2)
    ws_age = runtime.get("ws_book_age_s")
    if ws_age is not None:
        try:
            return round(float(ws_age), 2)
        except (TypeError, ValueError):
            pass
    return None


def _inventory_label_line(rt: Dict[str, Any]) -> str:
    label = str(rt.get("inventory_label") or "—")
    xrp_pct = rt.get("inventory_xrp_ratio_pct")
    target_pct = rt.get("inventory_target_xrp_pct")
    if target_pct is None:
        target_ratio = rt.get("inventory_target_xrp_ratio")
        if target_ratio is not None:
            try:
                target_pct = round(float(target_ratio) * 100.0, 1)
            except (TypeError, ValueError):
                target_pct = 55.0
        else:
            target_pct = 55.0
    if xrp_pct is not None:
        try:
            return f"{label} ({float(xrp_pct):.1f}% XRP vs {float(target_pct):.0f}% target)"
        except (TypeError, ValueError):
            pass
    return label


def _intent_operator_label(intent: str) -> str:
    key = (intent or "").lower()
    extras = {
        "solo_accumulate_on_edge": "accumulate on edge",
        "inventory_unload": "trim-only fallback",
        "patient_solo": "patient solo",
        "two_sided_skim": "two-sided skim",
        "hold_off": "hold off",
    }
    suffix = extras.get(key, "")
    display = key or "—"
    return f"{display} ({suffix})" if suffix else display


def _pause_cause_label(cause: str) -> str:
    cause = (cause or "").strip().lower()
    if not cause:
        return ""
    mapping = {
        "edge": "edge_gate",
        "intent": "intent",
        "bleed": "bleed",
        "inventory": "inventory",
        "tape": "tape",
        "operator": "operator",
    }
    return mapping.get(cause, cause)


def _decision_state_lines(rt: Dict[str, Any]) -> List[str]:
    try:
        from experimental.ws_feed.qd_hud import build_qd_hud_fields

        hud = build_qd_hud_fields(rt)
    except Exception:
        hud = {}

    snap = hud.get("qd_snapshot") or {}
    summary = hud.get("qd_decision_summary") or {}
    bid = snap.get("bid") or {}
    ask = snap.get("ask") or {}

    intent = str(snap.get("intent") or rt.get("qd_intent") or "—")
    intent_reason = str(snap.get("intent_reason") or rt.get("qd_intent_reason") or "—")

    bid_allowed = rt.get("qd_bid_allowed", bid.get("allowed"))
    ask_allowed = rt.get("qd_ask_allowed", ask.get("allowed"))
    bid_cause = _pause_cause_label(str(rt.get("qd_bid_pause_cause") or bid.get("block_cause") or ""))
    ask_cause = _pause_cause_label(str(rt.get("qd_ask_pause_cause") or ask.get("block_cause") or ""))

    bid_bps = bid.get("implied_bps") or rt.get("qd_bid_implied_bps")
    ask_bps = ask.get("implied_bps") or rt.get("qd_ask_implied_bps")
    bid_viable = bid.get("edge_viable", rt.get("qd_bid_edge_viable"))
    ask_viable = ask.get("edge_viable", rt.get("qd_ask_edge_viable"))

    bid_bleed = bool(bid.get("bleeding") or rt.get("qd_bid_bleeding"))
    ask_bleed = bool(ask.get("bleeding") or rt.get("qd_ask_bleeding"))
    bleed_active = bool(summary.get("protection_active") or bid_bleed or ask_bleed)

    inv_cb = snap.get("inventory_cb_mode") or rt.get("qd_inventory_cb_mode") or "—"
    inv_cb_label = snap.get("inventory_cb_label") or inv_cb

    lines = [
        f"Active Intent: {_intent_operator_label(intent)}",
        f"Reason: {intent_reason}",
        "",
        "L5 Permissions:",
    ]
    bid_line = f"- bid_allowed: {str(bid_allowed).lower()}"
    if bid_cause and bid_allowed is not True:
        bid_line += f" ({bid_cause})"
    ask_line = f"- ask_allowed: {str(ask_allowed).lower()}"
    if ask_cause and ask_allowed is not True:
        ask_line += f" ({ask_cause})"
    lines.extend([bid_line, ask_line, ""])

    edge_lines = ["Edge Gate Status:"]
    if bid_bps is not None:
        edge_lines.append(f"- bid: {float(bid_bps):.2f} bps ({'viable' if bid_viable else 'below threshold'})")
    if ask_bps is not None:
        edge_lines.append(f"- ask: {float(ask_bps):.2f} bps ({'viable' if ask_viable else 'below threshold'})")
    if bid_bps is not None and ask_bps is not None and not bid_viable and not ask_viable:
        edge_lines.append(f"- Both sides currently below solo threshold (~{float(bid_bps):.2f} bps)")
    if not bid_viable and not ask_viable and (bid_bps is not None or ask_bps is not None):
        edge_lines.append("- Solo edge gate: blocking")
    elif bid_viable or ask_viable:
        edge_lines.append("- Solo edge gate: passing on at least one side")
    lines.extend(edge_lines)
    lines.extend([
        "",
        f"Bleed Protection: {'Active' if bleed_active else 'Not active'}",
        "",
        f"Inventory Circuit Breaker: {inv_cb_label}",
    ])
    if str(inv_cb) == "skipped_solo":
        lines[-1] = "Inventory Circuit Breaker: Skipped (solo_book)"
    return lines


def _hourly_trend_bullets(logs: Path, *, hours: int = 24) -> List[str]:
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(hours=hours)
    fill_buckets: Dict[str, int] = defaultdict(int)
    toxic_recent: List[float] = []
    positive_hours = 0

    for path in sorted(logs.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if "WS pure fill" not in (row.get("notes") or ""):
                        continue
                    ts_raw = row.get("timestamp_utc") or ""
                    try:
                        ts = datetime.fromisoformat(ts_raw.strip().replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if ts < since:
                        continue
                    hk = ts.strftime("%Y-%m-%d %H:00")
                    fill_buckets[hk] += 1
                    try:
                        float(row.get("profit_xrp_equiv") or 0)
                    except (TypeError, ValueError):
                        pass
        except OSError:
            continue

    intel_path = logs / "intel_decisions.jsonl"
    if intel_path.exists():
        for line in intel_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("kind") != "cycle":
                continue
            ts_raw = str(row.get("ts_utc") or "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts < since:
                continue
            t30 = row.get("toxic_fill_ratio_30s")
            if t30 is not None:
                try:
                    toxic_recent.append(float(t30))
                except (TypeError, ValueError):
                    pass

    fill_counts = list(fill_buckets.values()) if fill_buckets else [0]
    max_fills = max(fill_counts) if fill_counts else 0
    low_activity = max_fills <= 3

    hour_caps: Dict[str, float] = defaultdict(float)
    for path in sorted(logs.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if "WS pure fill" not in (row.get("notes") or ""):
                        continue
                    ts_raw = row.get("timestamp_utc") or ""
                    try:
                        ts = datetime.fromisoformat(ts_raw.strip().replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if ts < since:
                        continue
                    hk = ts.strftime("%Y-%m-%d %H:00")
                    try:
                        hour_caps[hk] += float(row.get("profit_xrp_equiv") or 0)
                    except (TypeError, ValueError):
                        pass
        except OSError:
            continue
    positive_hours = sum(1 for v in hour_caps.values() if v > 0)

    bullets = []
    if low_activity:
        bullets.append(f"- Very low activity in recent hours (mostly 0–{max(3, max_fills)} fills)")
    else:
        bullets.append(f"- Recent fill activity up to {max_fills} fills/hour")
    if toxic_recent and max(toxic_recent) <= 0.01:
        bullets.append("- No toxic fills in the current window")
    elif toxic_recent:
        bullets.append(f"- Toxic@30s max {max(toxic_recent) * 100:.1f}% in window")
    else:
        bullets.append("- No toxic fills in the current window")
    if positive_hours <= 2:
        bullets.append("- Positive capture remains sparse")
    else:
        bullets.append(f"- Positive capture in {positive_hours} of last {hours}h buckets")
    return bullets


def _runtime_snapshot_lines(rt: Dict[str, Any]) -> List[str]:
    keys = [
        "version",
        "ws_as_version",
        "fills_session",
        "session_fill_count",
        "session_spread_capture_xrp",
        "session_pnl_balance_xrp",
        "portfolio_value_xrp",
        "cancel_per_fill",
        "toxic_fill_ratio",
        "toxic_fill_ratio_30s",
        "mean_markout_30s_pct",
        "effective_quote_age_at_fill_seconds",
        "g7_summary",
        "g7_scaler_label",
        "g2_grade",
        "g2_spread_mult",
        "g2_scaler_label",
        "bid_touch_backoff_bps",
        "ask_touch_backoff_bps",
        "worst_vs_touch_bps",
        "quote_visibility_summary",
        "quotes_at_touch",
        "inventory_label",
        "g6_activation_tier",
        "as_presence_pct",
        "mid_price",
        "dry_run",
        "trading_enabled",
        "cycle_count",
    ]
    lines = ["--- runtime_state (session + G7/G2) ---"]
    for k in keys:
        if k in rt and rt[k] is not None and rt[k] != "":
            lines.append(f"  {k}: {rt[k]}")
    return lines


def _intel_queue_review_lines(logs: Path, *, tail: int = 2000) -> List[str]:
    path = logs / "intel_decisions.jsonl"
    if not path.exists():
        return ["--- intel_decisions.jsonl ---", "  MISSING"]

    cycles: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("kind") == "cycle":
            cycles.append(row)

    if not cycles:
        return ["--- intel_decisions.jsonl ---", "  No cycle rows in tail."]

    versions = Counter(str(c.get("ws_as_version") or "?") for c in cycles)
    g2 = Counter(str(c.get("g2_grade") or "") for c in cycles)
    inv = Counter(str(c.get("inventory_label") or "") for c in cycles)
    wq = sum(1 for c in cycles if c.get("would_quote"))
    g2_on = sum(1 for c in cycles if c.get("g2_active"))
    last = cycles[-1]

    lines = [
        f"--- intel_decisions.jsonl (last {len(cycles)} cycles) ---",
        f"  ws_as_version: {dict(versions)}",
        f"  would_quote: {100.0 * wq / len(cycles):.1f}% ({wq}/{len(cycles)})",
        f"  g2_active: {100.0 * g2_on / len(cycles):.1f}%",
        f"  g2_grades: {dict(g2)}",
        f"  inventory_label: {dict(inv)}",
        (
            f"  last cycle: {last.get('cycle')} toxic@30s={last.get('toxic_fill_ratio_30s')} "
            f"markout@30s={last.get('mean_markout_30s_pct')} fills_session={last.get('fills_session')}"
        ),
    ]
    return lines


def _offer_refresh_lines(logs: Path) -> List[str]:
    placed = cancelled = refreshes = 0
    for path in sorted(logs.glob("trades_*.csv")):
        try:
            rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
        except OSError:
            continue
        for row in rows:
            if (row.get("event_type") or "").upper() != "OFFER_REFRESH":
                continue
            refreshes += 1
            notes = row.get("notes") or ""
            if "placed" in notes:
                try:
                    placed += int(notes.split("placed", 1)[1].split()[0])
                except (IndexError, ValueError):
                    pass
            if "cancelled" in notes:
                try:
                    part = notes.split("cancelled", 1)[1].split(",")[0].strip()
                    cancelled += int(part)
                except (IndexError, ValueError):
                    pass
    ratio = cancelled / max(1, placed)
    return [
        "--- OFFER_REFRESH (all trades_*.csv) ---",
        f"  refresh_events: {refreshes} | placed: {placed} | cancelled: {cancelled}",
        f"  cancel/place ratio: {ratio:.2f} (runtime cancel_per_fill is session fills)",
    ]


def build_operator_summary(
    *,
    logs_dir: Optional[Path] = None,
    report_id: str = "soak_dashboard",
) -> str:
    """Sections 1–3: operator-facing soak summary with layered QD state."""
    logs = logs_dir or (ROOT / "logs")
    rt = _load_runtime(logs)
    version = str(rt.get("ws_as_version") or rt.get("version") or "—")
    generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = "SOAK DASHBOARD + NARRATIVE" if report_id == "soak_dashboard_narrative" else "SOAK DASHBOARD — facts"

    if not rt:
        return (
            f"{title}\n"
            f"Generated: {generated} | Version: {version}\n"
            f"Report ID: {report_id}\n\n"
            "MISSING logs/runtime_state.json — start ws-engine or wait for first cycle.\n"
        )

    intel = _intel_cycle_window(logs)
    cycles = intel["cycles"]
    wq_pct, wq_n, wq_total = _would_quote_window_pct(cycles)
    window_label = wq_total if wq_total else int(rt.get("cycle_count") or 0)
    if wq_total:
        wq_display = f"{wq_pct:.1f}% ({wq_n}/{wq_total} cycles)"
    else:
        wq_display = f"{float(rt.get('as_presence_pct') or 0):.1f}% (runtime)"

    fills_session = rt.get("fills_session")
    if fills_session is None:
        fills_session = rt.get("session_fill_count", 0)

    markout = rt.get("mean_markout_30s_pct")
    toxic = rt.get("toxic_fill_ratio_30s")
    if toxic is None:
        toxic = rt.get("toxic_fill_ratio")

    book_mode = str(rt.get("qd_book_mode") or "—")
    peer = str(rt.get("qd_peer_lane_token") or rt.get("peer_lane_token") or "empty")
    solo = rt.get("solo_mode")
    posture = str(rt.get("posture_reason") or rt.get("qd_posture_reason") or "—")

    age_report = build_fill_age_report(logs_dir=logs)
    book_p95 = _book_age_p95(cycles, rt)
    lifetime_fills = count_ws_fills_csv(logs.parent if logs.name == "logs" else logs)

    buf = io.StringIO()
    buf.write(f"{title}\n")
    buf.write(f"Generated: {generated} | Version: {version}\n")
    buf.write(f"Report ID: {report_id}\n")

    buf.write(_section("1. Runtime & Session Overview"))
    buf.write(f"Version: {version}\n")
    buf.write(f"Trading Enabled: {rt.get('trading_enabled', '—')}\n")
    buf.write(f"Cycle Count (current window): {window_label}\n")
    buf.write(f"Would Quote: {wq_display}\n")
    buf.write(f"Inventory Label: {_inventory_label_line(rt)}\n")
    port = rt.get("portfolio_value_xrp")
    if port is not None:
        buf.write(f"Portfolio Value: {float(port):.3f} XRP\n")
    buf.write(f"Session Fills: {fills_session}\n")
    cap = rt.get("session_spread_capture_xrp")
    buf.write(f"Session Spread Capture: {float(cap or 0):.1f} XRP\n")
    if markout is not None:
        try:
            buf.write(f"Mean Markout @30s: {float(markout):.1f}%\n")
        except (TypeError, ValueError):
            buf.write(f"Mean Markout @30s: {markout}\n")
    else:
        buf.write("Mean Markout @30s: 0.0%\n")
    if toxic is not None:
        try:
            buf.write(f"Toxic Fill Ratio: {float(toxic) * 100:.1f}%\n")
        except (TypeError, ValueError):
            buf.write(f"Toxic Fill Ratio: {toxic}\n")
    else:
        buf.write("Toxic Fill Ratio: 0.0%\n")
    buf.write("\n")
    buf.write(f"Book Mode: {book_mode.title()} (peer_lane={peer})\n")
    buf.write(f"Solo Mode: {'Active' if solo else 'Off'}\n")
    buf.write(f"Posture Reason: {posture}\n")

    buf.write(_section("2. Current Decision State"))
    buf.write("\n".join(_decision_state_lines(rt)))
    buf.write("\n")

    buf.write(_section("3. Soak & Health Metrics"))
    buf.write(f"WS Fills (Session): {fills_session}\n")
    buf.write(f"Lifetime WS Fills: {lifetime_fills}\n")
    if age_report.age_seconds_p95 is not None:
        buf.write(f"Fill Quote Age (p95): {age_report.age_seconds_p95}s\n")
    else:
        buf.write("Fill Quote Age (p95): —\n")
    if book_p95 is not None:
        buf.write(f"Book Age (p95): {book_p95}s\n")
    else:
        buf.write("Book Age (p95): —\n")
    buf.write(f"Would Quote (current window): {wq_pct:.1f}%\n" if wq_total else f"Would Quote (runtime): {rt.get('as_presence_pct', '—')}%\n")
    buf.write("\nHourly Trend (last 24h):\n")
    for bullet in _hourly_trend_bullets(logs):
        buf.write(f"{bullet}\n")

    return buf.getvalue()


def build_soak_dashboard_facts(*, logs_dir: Optional[Path] = None) -> str:
    """Operator summary plus technical appendix (no Grok)."""
    logs = logs_dir or (ROOT / "logs")
    buf = io.StringIO()
    buf.write(build_operator_summary(logs_dir=logs, report_id="soak_dashboard"))

    rt_path = logs / "runtime_state.json"
    if not rt_path.exists():
        return buf.getvalue()

    rt = json.loads(rt_path.read_text(encoding="utf-8"))

    buf.write(_section("Technical appendix — runtime + gates"))
    buf.write("\n".join(_runtime_snapshot_lines(rt)))
    buf.write("\n")

    buf.write(_section("Fill quote age (detail)"))
    age_report = build_fill_age_report(logs_dir=logs)
    buf.write(format_fill_age_report(age_report))
    buf.write("\n")

    buf.write(_section("WS runtime analysis + C2 gate"))
    analysis = run_runtime_analysis(path=rt_path, include_backups=False, logs_dir=logs)
    buf.write(format_runtime_analysis_report(analysis, path_label=str(rt_path)))
    if analysis.soak:
        status = "PASS" if analysis.soak.passed else "FAIL"
        buf.write(f"\nC2 soak gate: {status} — {analysis.soak.failures}\n")

    buf.write(_section("G6 activation grade"))
    g6 = build_g6_report(runtime_path=rt_path, logs_dir=logs)
    buf.write(format_g6_report(g6))
    buf.write(f"\nG6 gate: {'PASS' if g6.passed else 'FAIL'}\n")

    buf.write(_section("Hourly soak trend (24h UTC)"))
    buf.write(format_hourly_soak_trend(logs_dir=logs))
    buf.write("\n")

    buf.write(_section("Queue / fill review"))
    buf.write("\n".join(_intel_queue_review_lines(logs)))
    buf.write("\n")
    buf.write("\n".join(_offer_refresh_lines(logs)))
    buf.write("\n")

    buf.write(_section("Discipline note"))
    buf.write(
        "Pure A-S reservation is sacred. Layered QD (L1–L5) is sole quoting authority. "
        "Skim Δ = trading edge; Wallet Δ / Port include spot MTM. "
        "Narrative explains — it does not override strategy.\n"
    )

    return buf.getvalue()


def fetch_grok_soak_narrative(
    facts: str,
    *,
    api_key: str,
    model: str = "grok-3",
    timeout_s: float = 45.0,
) -> str:
    """Call Grok API with discipline-bound soak narrative prompt."""
    import requests

    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    fact_body = facts if len(facts) <= 12000 else facts[:12000] + "\n\n[... truncated for token limit ...]"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": SOAK_NARRATIVE_PROMPT + fact_body}],
        "max_tokens": 500,
        "temperature": 0.3,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    choice = resp.json().get("choices", [{}])[0] or {}
    content = (choice.get("message") or {}).get("content") or ""
    return content.strip() or "(Grok returned empty narrative.)"


def build_soak_dashboard_report(
    *,
    logs_dir: Optional[Path] = None,
    narrative: bool = False,
    grok_key: str = "",
    grok_model: str = "grok-3",
    grok_enabled: bool = True,
) -> str:
    """Operator summary; narrative appends Grok advisory section."""
    if not narrative:
        return build_soak_dashboard_facts(logs_dir=logs_dir)

    summary = build_operator_summary(logs_dir=logs_dir, report_id="soak_dashboard_narrative")
    buf = io.StringIO()
    buf.write(summary)
    buf.write(_section("4. Grok Narrative (Advisory)"))

    if not grok_enabled:
        buf.write("Grok disabled (ws_hud_grok_enabled=false).\n")
        return buf.getvalue()

    key = (grok_key or "").strip()
    if not key:
        buf.write(
            "No Grok API key configured. Set XLG_GROK_KEY in .env or Config tab → Apply, "
            "then refresh this report.\n"
        )
        return buf.getvalue()

    try:
        narrative_text = fetch_grok_soak_narrative(summary, api_key=key, model=grok_model or "grok-3")
        buf.write(narrative_text)
        buf.write("\n")
    except Exception as exc:
        buf.write(f"Grok narrative failed: {type(exc).__name__}: {exc}\n")

    return buf.getvalue()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Soak dashboard report (facts + optional Grok narrative)")
    parser.add_argument("--narrative", action="store_true", help="Append Grok narrative (requires API key)")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    args = parser.parse_args()

    grok_key = ""
    grok_model = "grok-3"
    if args.narrative:
        from utils.env_secrets import resolve_intel_ai_config

        prov, grok_key, grok_model = resolve_intel_ai_config()

    text = build_soak_dashboard_report(
        logs_dir=args.logs_dir,
        narrative=args.narrative,
        grok_key=grok_key,
        grok_model=grok_model,
    )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
