"""
Phase A3 — Grok advisory A-S calibration (tune, do not quote).

Bundles live runtime (A2) + sacred corpus presence + competitor intel into one
structured Grok call. Returns suggested gamma/kappa/vol hints for the operator
to trial via live tester + grokster — never mutates would_quote or reservation.

Usage:
  python -m experimental.as_calibration_grok --key xai-...
  python -m experimental.as_calibration_grok --dry-run
  set XLG_GROK_KEY=xai-... && python -m experimental.as_calibration_grok
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from utils.env_secrets import resolve_grok_key
from experimental.ws_runtime_analysis import (
    analyze_samples,
    collect_samples,
    load_runtime_json,
    run_runtime_analysis,
)
from experimental.sacred_economics import load_decision_lines, resolve_trades_path

_REPO = Path(__file__).resolve().parents[1]
_GENERATED_RE = re.compile(r"Generated\s+(\d+)", re.I)


@dataclass
class CalibrationRecommendation:
    market_regime: str = "unknown"
    competitor_read: str = ""
    primary_blocker: str = ""
    suggested_gamma: float = 0.35
    suggested_kappa: float = 3.5
    suggested_volatility_pct_hint: float = 0.5
    pressure_interpretation: str = ""
    implementation_notes: List[str] = field(default_factory=list)
    hypothesis: str = ""
    confidence: float = 0.0
    what_to_measure_next: str = ""
    rationale: str = ""
    source: str = "grok"
    raw: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "market_regime": self.market_regime,
            "competitor_read": self.competitor_read,
            "primary_blocker": self.primary_blocker,
            "suggested_gamma": self.suggested_gamma,
            "suggested_kappa": self.suggested_kappa,
            "suggested_volatility_pct_hint": self.suggested_volatility_pct_hint,
            "pressure_interpretation": self.pressure_interpretation,
            "implementation_notes": list(self.implementation_notes),
            "hypothesis": self.hypothesis,
            "confidence": self.confidence,
            "what_to_measure_next": self.what_to_measure_next,
            "rationale": self.rationale,
            "source": self.source,
        }


def sacred_presence_snapshot(
    *,
    gamma: float,
    kappa: float,
    decisions_path: Path,
    window: int = 2000,
) -> Dict[str, Any]:
    """Compact sacred corpus presence for calibration brief (no Grok)."""
    from experimental.pure_as_quote_path import would_quote_pure
    from strategy.avellaneda_strategy import AvellanedaStrategy

    max_lines = window if window > 0 else None
    lines = load_decision_lines(decisions_path, max_lines)
    total = len(lines)
    if total == 0:
        return {"error": "no decision lines", "path": str(decisions_path)}

    as_strat = AvellanedaStrategy(None, gamma=gamma, kappa=kappa)
    baseline_presence = 0
    pure_presence = 0
    for ln in lines:
        try:
            d = json.loads(ln)
            reasons = " ".join(e.get("message", "") for e in d.get("events", []))
        except json.JSONDecodeError:
            continue
        m = _GENERATED_RE.search(reasons)
        if m and int(m.group(1)) > 0:
            baseline_presence += 1
        if would_quote_pure(as_strat, ln):
            pure_presence += 1

    return {
        "decision_window": total,
        "baseline_presence_pct": round(100.0 * baseline_presence / total, 1),
        "pure_as_presence_pct": round(100.0 * pure_presence / total, 1),
        "gamma": gamma,
        "kappa": kappa,
        "note": "Sacred VPS hard-gate corpus; pure presence is replay oracle not live fills.",
    }


def grokster_fill_calibration_hint(trades_path: Optional[Path]) -> Dict[str, Any]:
    """Heuristic gamma/kappa from sacred fill rate (same idea as grokster)."""
    if not trades_path or not trades_path.exists():
        return {}
    from experimental.sacred_economics import load_trades_rows

    rows = load_trades_rows(trades_path)
    fills = [r for r in rows if (r.get("event_type") or "").upper() in ("BUY", "SELL")]
    fill_count = len(fills)
    if fill_count <= 0:
        return {}
    cycles = 6226.0
    arrival_rate = fill_count / cycles
    return {
        "fill_count": fill_count,
        "suggested_gamma_heuristic": 0.30 if fill_count > 300 else 0.40,
        "suggested_kappa_heuristic": round(max(2.0, min(5.0, 1.0 / max(arrival_rate, 0.01) * 0.8)), 2),
    }


def build_calibration_brief(
    *,
    runtime_path: Path,
    gamma: float,
    kappa: float,
    include_backups: bool = False,
    sacred_window: int = 2000,
    decisions_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Assemble context dict for Grok (and dry-run display)."""
    runtime: Dict[str, Any] = {}
    if runtime_path.exists():
        runtime = load_runtime_json(runtime_path)

    a2 = run_runtime_analysis(path=runtime_path, include_backups=include_backups)
    decisions_path = decisions_path or Path("logs/decisions.jsonl")
    sacred = sacred_presence_snapshot(
        gamma=gamma,
        kappa=kappa,
        decisions_path=decisions_path,
        window=sacred_window,
    )
    trades_path = resolve_trades_path(decisions_path.parent)
    fill_hint = grokster_fill_calibration_hint(trades_path)

    top_competitors = runtime.get("top_competitors") or []
    comp_summary = [
        {
            "account": (c.get("account_full") or c.get("account", ""))[:16],
            "last_spread_pct": c.get("last_spread"),
            "activity": c.get("activity"),
            "sides": c.get("sides"),
        }
        for c in top_competitors[:5]
    ]

    snapshot = {
        "current_params": {"gamma": gamma, "kappa": kappa},
        "live_snapshot": {
            "mid": runtime.get("mid_price"),
            "best_bid": runtime.get("best_bid_rlusd_per_xrp"),
            "best_ask": runtime.get("best_ask_rlusd_per_xrp"),
            "book_spread_pct": runtime.get("book_spread_pct"),
            "as_reservation": runtime.get("as_reservation"),
            "as_optimal_spread_pct": runtime.get("as_optimal_spread_pct"),
            "would_quote_now": runtime.get("market_edge_met"),
            "session_presence_pct": runtime.get("as_presence_pct"),
            "inventory_label": runtime.get("inventory_label"),
            "volatility_pct": runtime.get("volatility_pct"),
            "ws_book_age_s": runtime.get("ws_book_age_s"),
            "sample_history_count": len(runtime.get("sample_history") or []),
        },
        "competitor_intel": {
            "pressure": runtime.get("competitor_pressure"),
            "observed_spread_pct": runtime.get("competitor_observed_spread_pct"),
            "depth_xrp": runtime.get("competitor_depth_xrp"),
            "num_active_mms": runtime.get("num_active_mms"),
            "skim_advice": runtime.get("competitor_skim_advice"),
            "top_competitors": comp_summary,
        },
        "a2_analysis": a2.as_dict(),
        "sacred_corpus": sacred,
        "grokster_heuristic": fill_hint,
        "implementation_truth": {
            "kappa_in_spread_formula": False,
            "quoting_guard": "reservation strictly inside best_bid and best_ask",
            "grok_role": "advisory calibration only — never sets would_quote",
            "book_anchor_fraction": 0.55,
            "min_spread_floor_pct": 0.04,
        },
    }
    return snapshot


def build_calibration_prompt(brief: Dict[str, Any]) -> str:
    brief_json = json.dumps(brief, indent=2, default=str)
    return (
        "You are calibrating a pure Avellaneda-Stoikov market maker on XRPL XRP/RLUSD.\n"
        "Your job is ADVISORY ONLY: recommend parameter trials. You must NOT decide to quote.\n"
        "The bot's quoting guard is fixed: reservation must be inside live best bid/ask.\n\n"
        "Context (live WS runtime + A2 stats + sacred corpus replay + competitors):\n"
        f"{brief_json}\n\n"
        "Analyze the live market, competitor behavior, and why would_quote may be 0%.\n"
        "Note: kappa is logged but may not yet affect spread math — say so if relevant.\n"
        "Recommend gamma/kappa/volatility_pct trials the operator should run next.\n\n"
        "Return ONLY valid JSON (no markdown) with exactly these keys:\n"
        "{\n"
        '  "market_regime": "tight" | "normal" | "defensive",\n'
        '  "competitor_read": "<1-3 sentences on what competitors are doing>",\n'
        '  "primary_blocker": "<main reason for 0 quotes if applicable>",\n'
        '  "suggested_gamma": <float 0.15-0.60>,\n'
        '  "suggested_kappa": <float 2.0-6.0>,\n'
        '  "suggested_volatility_pct_hint": <float 0.0-2.0>,\n'
        '  "pressure_interpretation": "<how to read competitor_pressure for tuning>",\n'
        '  "implementation_notes": ["<note about book anchor/floors/kappa wiring>", "..."],\n'
        '  "hypothesis": "<what changing params should fix>",\n'
        '  "confidence": <float 0.0-1.0>,\n'
        '  "what_to_measure_next": "<specific metrics after next 300s trial>",\n'
        '  "rationale": "<2-4 sentences tying live + sacred data to recommendations>"\n'
        "}\n"
    )


def _extract_json_object(text: str) -> Dict[str, Any]:
    content = (text or "").strip()
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        content = content.replace("json", "", 1).strip()
    return json.loads(content)


def parse_calibration_response(data: Dict[str, Any], *, source: str = "grok") -> CalibrationRecommendation:
    notes = data.get("implementation_notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return CalibrationRecommendation(
        market_regime=str(data.get("market_regime", "unknown")),
        competitor_read=str(data.get("competitor_read", "")),
        primary_blocker=str(data.get("primary_blocker", "")),
        suggested_gamma=float(data.get("suggested_gamma", 0.35)),
        suggested_kappa=float(data.get("suggested_kappa", 3.5)),
        suggested_volatility_pct_hint=float(data.get("suggested_volatility_pct_hint", 0.5)),
        pressure_interpretation=str(data.get("pressure_interpretation", "")),
        implementation_notes=[str(n) for n in notes],
        hypothesis=str(data.get("hypothesis", "")),
        confidence=float(data.get("confidence", 0.0)),
        what_to_measure_next=str(data.get("what_to_measure_next", "")),
        rationale=str(data.get("rationale", "")),
        source=source,
        raw=dict(data),
    )


def call_grok_calibration(
    *,
    api_key: str,
    brief: Dict[str, Any],
    model: str = "grok-3",
    timeout: int = 60,
) -> CalibrationRecommendation:
    prompt = build_calibration_prompt(brief)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.3,
    }
    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    data = _extract_json_object(content)
    return parse_calibration_response(data, source=f"grok:{model}")


def validation_commands(rec: CalibrationRecommendation, *, seconds: int = 300) -> List[str]:
    g = rec.suggested_gamma
    k = rec.suggested_kappa
    return [
        (
            f"python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds {seconds} "
            f"--sample-interval 4 --gamma {g:.2f} --kappa {k:.2f} --profile tight_spread --verbose"
        ),
        "python -m experimental.ws_runtime_analysis",
        f"python experimental/grokster.py --gamma {g:.2f} --kappa {k:.2f} --window 2000 --no-ab",
        f"python -m experimental.as_calibration_grok --gamma {g:.2f} --kappa {k:.2f}",
    ]


def format_calibration_report(
    rec: CalibrationRecommendation,
    *,
    brief: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> str:
    lines = [
        "=== A-S CALIBRATION (Grok advisory - tune, do not quote) ===",
        "",
    ]
    if dry_run:
        lines.append("Mode: DRY RUN (no Grok API call). Brief summary below.")
        lines.append("")
    if brief:
        live = brief.get("live_snapshot") or {}
        a2 = brief.get("a2_analysis") or {}
        sacred = brief.get("sacred_corpus") or {}
        lines.extend(
            [
                "--- Context summary ---",
                f"Live would_quote now: {live.get('would_quote_now')} | session presence: {live.get('session_presence_pct')}%",
                f"Book spread: {live.get('book_spread_pct')}% | A-S optimal: {live.get('as_optimal_spread_pct')}%",
                f"A2 samples: {a2.get('sample_count', 0)} | live presence: {a2.get('would_quote_pct', 0):.1f}%",
                f"Sacred pure presence (gamma={sacred.get('gamma')}): {sacred.get('pure_as_presence_pct')}%",
                "",
            ]
        )
    lines.extend(
        [
            "--- Grok recommendation (trial these - operator validates) ---",
            f"Regime: {rec.market_regime} | confidence: {rec.confidence:.2f}",
            f"Primary blocker: {rec.primary_blocker or 'n/a'}",
            f"Suggested gamma: {rec.suggested_gamma:.2f} | kappa: {rec.suggested_kappa:.2f} | vol hint: {rec.suggested_volatility_pct_hint:.2f}%",
            "",
            f"Competitor read: {rec.competitor_read}",
            f"Pressure: {rec.pressure_interpretation}",
            f"Hypothesis: {rec.hypothesis}",
            f"Rationale: {rec.rationale}",
            f"Measure next: {rec.what_to_measure_next}",
        ]
    )
    if rec.implementation_notes:
        lines.append("")
        lines.append("Implementation notes:")
        for n in rec.implementation_notes:
            lines.append(f"  - {n}")
    lines.extend(["", "--- Validation commands (copy after you approve trial) ---"])
    for cmd in validation_commands(rec):
        lines.append(cmd)
    lines.extend(
        [
            "",
            "Grok does NOT set would_quote. Compare trials with ws_runtime_analysis + grokster before checking in ws_as_calibration.yaml.",
        ]
    )
    return "\n".join(lines)


def run_calibration_session(
    *,
    runtime_path: Path,
    api_key: str = "",
    model: str = "grok-3",
    gamma: float = 0.35,
    kappa: float = 3.5,
    include_backups: bool = False,
    sacred_window: int = 2000,
    dry_run: bool = False,
) -> Tuple[CalibrationRecommendation, Dict[str, Any]]:
    brief = build_calibration_brief(
        runtime_path=runtime_path,
        gamma=gamma,
        kappa=kappa,
        include_backups=include_backups,
        sacred_window=sacred_window,
    )
    if dry_run or not api_key:
        rec = parse_calibration_response(
            {
                "market_regime": "dry_run",
                "competitor_read": "Skipped - use --key or XLG_GROK_KEY for live Grok calibration.",
                "primary_blocker": (brief.get("a2_analysis") or {}).get("zero_quote_reasons", {}),
                "suggested_gamma": gamma,
                "suggested_kappa": kappa,
                "suggested_volatility_pct_hint": brief.get("live_snapshot", {}).get("volatility_pct") or 0.5,
                "pressure_interpretation": str(brief.get("competitor_intel", {}).get("skim_advice", "")),
                "implementation_notes": [
                    "kappa may not affect spread until wired in avellaneda_strategy.py",
                    "book anchor 0.55 and min_spread floor often dominate 0-quote on tight books",
                ],
                "hypothesis": "Run with --key after a 300s tester session for real Grok read.",
                "confidence": 0.0,
                "what_to_measure_next": "would_quote_pct and zero_quote_reasons after param trial",
                "rationale": "Dry run shows bundled brief only.",
            },
            source="dry_run",
        )
        return rec, brief
    rec = call_grok_calibration(api_key=api_key, brief=brief, model=model)
    return rec, brief


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grok advisory A-S calibration (Phase A3): live market + competitors -> param trials"
    )
    parser.add_argument("--path", type=Path, default=Path("logs/ws_as_demo_runtime.json"))
    parser.add_argument("--key", default="", help="xAI API key (or set XLG_GROK_KEY env)")
    parser.add_argument("--model", default="grok-3")
    parser.add_argument("--gamma", type=float, default=0.35, help="Current gamma used in brief")
    parser.add_argument("--kappa", type=float, default=3.5, help="Current kappa used in brief")
    parser.add_argument("--include-backups", action="store_true")
    parser.add_argument("--sacred-window", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true", help="Build brief only; no Grok API call")
    parser.add_argument("--brief-json", action="store_true", help="Print full brief JSON")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print recommendation JSON")
    args = parser.parse_args()

    api_key = resolve_grok_key(args.key)
    rec, brief = run_calibration_session(
        runtime_path=args.path,
        api_key=api_key,
        model=args.model,
        gamma=args.gamma,
        kappa=args.kappa,
        include_backups=args.include_backups,
        sacred_window=args.sacred_window,
        dry_run=args.dry_run,
    )

    if args.brief_json:
        print(json.dumps(brief, indent=2, default=str))
        return
    if args.as_json:
        out = {"recommendation": rec.as_dict(), "validation_commands": validation_commands(rec)}
        print(json.dumps(out, indent=2))
        return
    print(format_calibration_report(rec, brief=brief, dry_run=args.dry_run or not api_key))


if __name__ == "__main__":
    main()
