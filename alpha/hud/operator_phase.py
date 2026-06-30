"""Operator phase — SKYNET strategy bias (trust / scale / aggressive)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

OPERATOR_PHASE_KEY = "alpha_operator_phase"

OPERATOR_PHASES: Tuple[str, ...] = ("trust", "scale", "aggressive")
DEFAULT_OPERATOR_PHASE = "trust"

_PHASE_META: Dict[str, Dict[str, str]] = {
    "trust": {
        "label": "Trust",
        "headline": "Prove behavior overnight — patient entries, minimize SL churn",
        "when": "New deploy, post-fix soak, or SL streak / underwater brackets",
        "skynet_bias": (
            "Patient accumulation. Prefer max_pending_buys↑ over buy_limit_offset_pct↓ when "
            "RLUSD-heavy + bullish TA. Do NOT lower offset below effective without explicit operator "
            "request or a sharp dip. weakness_deviation ≥ 0.05 typical. Judge edge from "
            "realized_bracket_pnl in SKYNET context (tp_exits/sl_exits, realized_profit_xrp_equiv), "
            "not session_pnl_xrp (MTM)."
        ),
    },
    "scale": {
        "label": "Scale",
        "headline": "Modest accumulation after trust earned",
        "when": "Clean nights, deferred SL working, ratio climbing toward target",
        "skynet_bias": (
            "Allow modest aggression: max_pending_buys 2–3, buy_offset 0.15–0.20, weakness 0.04, "
            "risk 2–3%. On rips with mild XRP-heavy dev (+0.05–0.08), alpha_accumulation_max_deviation "
            "and alpha_bull_run_max_deviation ~0.08 so accumulation can ARM. Still avoid stacking "
            "offset↓ + weakness↓ in one cycle. Widen drift before chasing entries if mid_passed_entry "
            "churn appears."
        ),
    },
    "aggressive": {
        "label": "Aggressive",
        "headline": "Bag-growth push toward high XRP ratio",
        "when": "Operator accepts churn; book healthy; TA supportive; bleed under control",
        "skynet_bias": (
            "Eager deploy: offset 0.08–0.12, drift > offset+spread (~0.35), risk toward guardrail max, "
            "max_pending 2–3. STOP increasing aggression after SL streak or negative realized P&L — "
            "revert to trust-phase knobs."
        ),
    },
}


def normalize_operator_phase(value: Any) -> str:
    if value is None:
        return DEFAULT_OPERATOR_PHASE
    phase = str(value).strip().lower()
    if phase in OPERATOR_PHASES:
        return phase
    aliases = {
        "patient": "trust",
        "prove": "trust",
        "soak": "trust",
        "balanced": "scale",
        "growth": "aggressive",
        "eager": "aggressive",
    }
    return aliases.get(phase, DEFAULT_OPERATOR_PHASE)


def phase_snapshot_fields(overrides: Dict[str, Any] | None) -> Dict[str, Any]:
    phase = normalize_operator_phase((overrides or {}).get(OPERATOR_PHASE_KEY))
    meta = _PHASE_META[phase]
    return {
        OPERATOR_PHASE_KEY: phase,
        "alpha_operator_phase_label": meta["label"],
    }


def build_operator_phase_context_block(phase: str) -> str:
    p = normalize_operator_phase(phase)
    meta = _PHASE_META[p]
    return "\n".join(
        [
            "=== Operator phase (PRIMARY strategy bias — overrides generic scenario defaults) ===",
            f"phase={p} ({meta['label']})",
            f"intent: {meta['headline']}",
            f"use_when: {meta['when']}",
            f"skynet_rules: {meta['skynet_bias']}",
            "",
            "Phase change: operator sets alpha_operator_phase in HUD (trust | scale | aggressive).",
            "Do NOT suggest changing phase unless operator explicitly asks to move phases.",
        ]
    )


def build_operator_phase_playbook() -> str:
    """Scenarios S–U — operator phase presets (pair with A–R)."""
    return """=== Operator phase scenarios (S–U) ===
Set via HUD `alpha_operator_phase` (trust | scale | aggressive). SKYNET must respect active phase.

S — Trust phase (default): prove overnight behavior, anti-bleed
  phase=trust · offset 0.20+ · weakness 0.05 · max_pending 1–2 · risk ~2% · deferred_sl on
  SKYNET: RLUSD-heavy + bullish + HOLD max_pending → raise cap, NOT offset↓/drift tighten
  Metrics: realized_bracket_pnl in context (tax CSV) — NOT session_pnl_xrp_mtm alone

T — Scale phase: modest accumulation after trust earned
  phase=scale · offset 0.15–0.20 · weakness 0.04 · max_pending 2–3 · risk 2–3% · drift 0.35 if sticky
  SKYNET: one knob at a time; max_pending before offset when cap blocks deploy

U — Aggressive phase: bag-growth push (guardrails still apply)
  phase=aggressive · offset 0.08–0.12 · drift 0.35 · max_pending 2–3 · risk toward guardrail max
  SKYNET: if recent SL streak or underwater brackets → recommend trust phase or defense, not more heat

Graduation: trust → scale after clean nights + ratio climbing; scale → aggressive only with operator OK.
"""


def phase_user_message_rules(phase: str) -> List[str]:
    p = normalize_operator_phase(phase)
    meta = _PHASE_META[p]
    lines = [
        f"6. OPERATOR PHASE active: {p} ({meta['label']}) — {meta['headline']}",
        f"   {meta['skynet_bias']}",
    ]
    if p == "trust":
        lines.append(
            "   In trust phase: do NOT suggest lowering alpha_buy_limit_offset_pct below the effective "
            "value unless operator explicitly asks or mid dumped 2%+."
        )
    elif p == "aggressive":
        lines.append(
            "   In aggressive phase: if brackets show SL-heavy recent exits, bias back toward trust knobs."
        )
    return lines
