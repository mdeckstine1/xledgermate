"""Alpha SKYNET — Phase 1 advisor (manual prompt + human-approved apply)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS, validate_override_updates
from alpha.orders.stale_pending import build_pending_buy_stale_snapshot
from alpha.hud.operator_phase import (
    OPERATOR_PHASE_KEY,
    build_operator_phase_context_block,
    normalize_operator_phase,
)
from alpha.hud.operator_market_regime import (
    OPERATOR_MARKET_REGIME_KEY,
    build_market_regime_context_block,
    normalize_market_regime,
)
from alpha.hud.skynet_knobs import build_skynet_knob_catalog, normalize_suggestion_key
from alpha.reporting.realized_pnl import build_realized_pnl_snapshot, format_realized_pnl_context_block
from alpha.hud.skynet_scenarios import (
    build_scenario_playbook,
    build_skynet_user_message,
    infer_scenario_hints,
)
from alpha.decision.accumulation_regime import build_accumulation_context_block
from alpha.decision.reload_regime import build_reload_context_block
from config.settings import BotConfig
from utils.env_secrets import resolve_grok_key

logger = logging.getLogger(__name__)

_SKYNET_LLM_ENDPOINT = "https://api.x.ai/v1/chat/completions"

_SKYNET_VOICE_RULES = """
Voice and tone (for JSON fields reasoning, summary, warnings — still valid JSON output):
- Write like a sharp XRPL desk buddy: plain English, short paragraphs, no corporate fluff.
- A little dry humor or light sarcasm is welcome when the tape deserves it — never cruel, never mocking the operator.
- summary = one punchy line the operator can skim; reasoning = walk through what the bot is doing and why in human terms.
- Translate jargon (deviation, max_pending, deferred SL) into what-it-means-for-the-bag.
- If last night was SL-heavy, say so bluntly and recommend defense — do not sugarcoat churn.
"""

_SYSTEM_PROMPT = """You are SKYNET, an expert advisor for xLedgerMate Alpha — an XRPL XRP/RLUSD limit-order bag-growth bot.

You advise the human operator only. You do NOT execute trades.
""" + _SKYNET_VOICE_RULES + """

Respond with a single JSON object (no markdown fences) using exactly this schema:
{{
  "reasoning": "<3-8 sentences in conversational plain language — personality OK>",
  "summary": "<one punchy headline for the operator>",
  "suggested_changes": [
    {{"key": "<operator_config_key>", "value": <json_value>, "reason": "<why>"}}
  ],
  "warnings": ["<optional safety warnings>"]
}}

Rules for suggested_changes:
- Only use keys from this allowlist: {allowed_keys}
- Use numeric types for numbers, booleans for true/false.
- inventory_target_xrp_ratio is 0.0-1.0 (not percent). The HUD also accepts target_xrp_pct as alias — prefer inventory_target_xrp_ratio.
- Do NOT suggest dry_run changes — the operator must toggle LIVE/dry-run manually.
- Prefer small, incremental knob adjustments aligned with bag growth and risk.
- If no changes are warranted, return an empty suggested_changes array.

Operator prompt priority (critical):
- The user message begins with OPERATOR PROMPT (PRIMARY). Your reasoning and summary MUST address it directly.
- Do NOT ignore operator market view, strategy, or goals in favor of automated scenario hints or playbook presets.
- Scenario playbook and likely_scenarios are REFERENCE ONLY — use when aligned with operator intent, not as a default template.
- HOLD due to max_pending_buys alone does NOT mean "tighten drift" — if operator wants bullish buy / RLUSD deployment, suggest accumulation knobs per operator phase (trust: max_pending↑ before offset↓; scale/aggressive: offset↓ may apply).
- Respect `alpha_operator_phase` in context (trust | scale | aggressive). Trust phase: do NOT lower alpha_buy_limit_offset_pct below effective without explicit operator ask or sharp dip.
- Respect `alpha_operator_market_regime` (bull | neutral | bear). Bear/neutral after SL streaks → defense first, not more bids.
- session_pnl_xrp is mark-to-market portfolio drift — NOT realized trading profit. Use bracket TP/SL outcomes when judging bleed.
- Context block `realized_bracket_pnl` (tax CSV) is authoritative for trading edge in trust phase — prefer over session_pnl_xrp_mtm.

- When explaining WATCHING vs ARMED, read `Engine gate diagnostics` and `Market structure` blocks — do not infer breakout thresholds from TA bias alone.
- `accumulation_dev_cap` FAIL means breakout can fire but accumulation stays blocked until dev eases or operator raises alpha_accumulation_max_deviation / alpha_bull_run_max_deviation (scale phase often uses 0.08).
- When the operator describes desired settings in natural language (e.g. "risk 4%", "stickier bids", "max pending 1", "bullish consolidation buy"), translate into concrete suggested_changes — do not answer with unrelated scenario C presets.
- Pending buy limits are passive: they fill when best ask hits the bid, NOT when mid crosses entry.
- Stale pending buy policy (see context `pending_buy_stale`):
  - `entry_drift` — |entry − target| / mid exceeds `alpha_stale_pending_buy_max_drift_pct`
  - `mid_passed_entry` — mid rallied above bid without fill beyond max drift (common when drift ≈ buy_offset — use Scenario G: widen drift)
  - `entry_above_mid` — bid above mid (off-policy)
  - `excess_pending_buy` — count > `alpha_max_pending_buys` (farthest pruned)
  - STICKY bids: set `alpha_stale_pending_buy_max_drift_pct` > `alpha_buy_limit_offset_pct` + spread (~0.35% when offset 0.12%).
  - CHASE bids: drift ≈ offset — expect frequent cancel/replace.
  - Cancels are one XRPL offer per engine cycle — clearing many bids takes minutes.
- When many pending buys sit unfilled, check `pending_buy_stale`; for ladder clutter tighten drift and max_pending; for entry churn widen drift (Scenario G).
- Prefer operator key names from allowlist; aliases like risk_per_trade_pct map to alpha_risk_per_trade_pct.
"""

# Phase 1: never auto-apply mode switches without dedicated HUD confirmations.
_BLOCKED_APPLY_KEYS = frozenset({"dry_run"})


def skynet_status(config: BotConfig | None = None) -> Dict[str, Any]:
    cfg = config or BotConfig.load()
    explicit = (getattr(cfg, "alpha_grok_api_key", "") or "").strip()
    key = resolve_grok_key(explicit)
    key_source = "config" if explicit else ("env" if key else "missing")
    model = (getattr(cfg, "alpha_skynet_grok_model", None) or "grok-3").strip() or "grok-3"
    max_tokens = int(getattr(cfg, "alpha_skynet_grok_max_tokens", 4096) or 4096)
    enabled = bool(getattr(cfg, "alpha_skynet_enabled", True))
    return {
        "enabled": enabled,
        "configured": bool(key),
        "key_source": key_source,
        "model": model,
        "max_tokens": max(256, min(8192, max_tokens)),
        "key_hint": f"xai-…{key[-4:]}" if len(key) >= 8 else "",
    }


def build_structure_context_block(
    structure: Dict[str, Any],
    *,
    mid: float = 0.0,
) -> str:
    """Market structure snapshot — primary input for breakout / drift arming."""
    if not structure:
        return "=== Market structure ===\n(not available — engine needs price history)"
    rh = float(structure.get("recent_high") or 0.0)
    rl = float(structure.get("recent_low") or 0.0)
    mean = float(structure.get("mean_mid") or 0.0)
    mid_f = float(structure.get("mid") or mid or 0.0)
    extra: list[str] = []
    if rh > 0 and mid_f > 0:
        extra.append(f"pct_below_recent_high={(rh - mid_f) / rh * 100.0:.3f}%")
    if mean > 0 and mid_f > 0:
        extra.append(f"pct_above_mean={(mid_f - mean) / mean * 100.0:.3f}%")
    lines = [
        "=== Market structure (breakout / drift arming uses this — not just TA) ===",
        f"trend={structure.get('trend')} breakout_up={structure.get('breakout_up')} breakout_down={structure.get('breakout_down')}",
        f"mid={mid_f:.6f} mean_mid={mean:.6f} recent_high={rh:.6f} recent_low={rl:.6f}",
        f"swing_high={structure.get('swing_high')} sample_count={structure.get('sample_count')}",
        f"summary={structure.get('summary') or ''}",
    ]
    if extra:
        lines.append(" | ".join(extra))
    cc = structure.get("confirmation_candle")
    if isinstance(cc, dict) and cc:
        lines.append(f"confirmation_candle={json.dumps(cc, default=str)[:400]}")
    return "\n".join(lines)


def build_gate_diagnostics_block(
    hud_state: Dict[str, Any],
    config: BotConfig,
) -> str:
    """Pre-compute engine threshold comparisons so SKYNET does not guess gate math."""
    inv = hud_state.get("inventory") or {}
    ta = hud_state.get("technical_analysis") or {}
    structure = hud_state.get("structure") or {}
    momentum = hud_state.get("momentum_entry") or {}
    tape = hud_state.get("tape_participation") or {}
    acc = hud_state.get("accumulation_regime") or {}
    decision = hud_state.get("decision") or {}
    execution = hud_state.get("execution") or {}

    dev = float(inv.get("deviation") or 0.0)
    weakness = float(config.alpha_weakness_deviation)
    accum_max = float(getattr(config, "alpha_accumulation_max_deviation", 0.04))
    bull_max = float(getattr(config, "alpha_bull_run_max_deviation", 0.02))
    ta_cfg = config.alpha_technical_analysis
    min_breakout = float(ta_cfg.min_breakout_score)
    min_buy = float(ta_cfg.min_buy_score)
    breakout_score = float(ta.get("breakout_score") or 0.0)
    buy_score = float(ta.get("buy_score") or 0.0)

    mid_f = float(hud_state.get("mid") or structure.get("mid") or 0.0)
    mean = float(structure.get("mean_mid") or 0.0)
    rh = float(structure.get("recent_high") or 0.0)
    drift_pct = float(getattr(config, "alpha_tape_uptrend_drift_pct", 0.25))
    drift_ok = mean > 0 and mid_f >= mean * (1.0 + drift_pct / 100.0)
    near_high_pct = float(getattr(config, "alpha_bull_run_near_high_pct", 0.06))
    near_high_ok = rh > 0 and mid_f >= rh * (1.0 - near_high_pct / 100.0)

    def _pass_fail(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    lines = [
        "=== Engine gate diagnostics (authoritative — compare numbers before advising patience) ===",
        (
            f"dip_only_gate: dev={dev:+.3f} need≤{-weakness:+.3f} → "
            f"{_pass_fail(dev <= -weakness)} (classic weakness buys)"
        ),
        (
            f"accumulation_dev_cap: dev={dev:+.3f} max={accum_max:+.3f} → "
            f"{_pass_fail(dev <= accum_max)} (blocks accumulation ARMED even on breakout)"
        ),
        (
            f"bull_run_dev_cap: dev={dev:+.3f} max={bull_max:+.3f} → "
            f"{_pass_fail(dev <= bull_max)} (momentum_entry path)"
        ),
        (
            f"ta_breakout: score={breakout_score:.2f} need≥{min_breakout:.2f} "
            f"confirmed={ta.get('breakout_confirmed')} → {_pass_fail(breakout_score >= min_breakout)}"
        ),
        (
            f"ta_buy_gate: buy={buy_score:.2f} min={min_buy:.2f} "
            f"entry_buy_allowed={ta.get('entry_buy_allowed')} bias={ta.get('bias')}"
        ),
        (
            f"structure_arm: trend={structure.get('trend')} breakout_up={structure.get('breakout_up')} "
            f"drift_ok={drift_ok} near_high_ok={near_high_ok}"
        ),
        f"momentum_entry: active={momentum.get('active')} reason={momentum.get('reason') or '—'}",
        (
            "tape_participation: "
            f"active={tape.get('active')} reason={tape.get('reason') or '—'} "
            "(waiver path — inactive when TA already bullish)"
        ),
        (
            f"accumulation: phase={acc.get('phase')} armed={acc.get('armed')} "
            f"entry_allowed={acc.get('entry_allowed')} blockers={acc.get('blockers')}"
        ),
        f"last_decision: action={decision.get('action')} reason={decision.get('reason')}",
    ]
    if execution:
        lines.append(
            f"last_execution: action={execution.get('action')} executed={execution.get('executed')} "
            f"message={execution.get('message')}"
        )
    cycle = hud_state.get("engine_cycle")
    if cycle is not None:
        lines.append(
            f"engine_cycle={cycle} interval_sec={int(config.alpha_cycle_interval_seconds)} "
            "(patience = cycles until signal, not wall-clock chop)"
        )
    return "\n".join(lines)


def _technical_analysis_context(ta: Dict[str, Any]) -> str:
    if not ta:
        return "=== Technical analysis ===\n(not evaluated)"
    payload = {
        k: ta.get(k)
        for k in (
            "enabled",
            "bias",
            "buy_score",
            "sell_score",
            "breakout_score",
            "breakout_confirmed",
            "entry_buy_allowed",
            "entry_sell_allowed",
            "summary",
            "rsi",
            "bb_bandwidth_pct",
        )
        if ta.get(k) is not None
    }
    return "=== Technical analysis ===\n" + json.dumps(payload, default=str)


def build_skynet_context(
    hud_state: Dict[str, Any],
    *,
    operator_config: Optional[Dict[str, Any]] = None,
    effective_config: Optional[BotConfig] = None,
) -> str:
    """Serialize rich operator context for the SKYNET advisor."""
    inv = hud_state.get("inventory") or {}
    risk = hud_state.get("risk") or {}
    decision = hud_state.get("decision") or {}
    mc = hud_state.get("market_conditions") or {}
    brackets = hud_state.get("brackets") or {}
    reentry = hud_state.get("reentry") or {}
    cfg = operator_config or hud_state.get("config_effective") or {}
    bot_cfg = effective_config or BotConfig.load()
    mid = float(hud_state.get("mid") or 0.0)
    structure = hud_state.get("structure") if isinstance(hud_state.get("structure"), dict) else {}
    ta = hud_state.get("technical_analysis") if isinstance(hud_state.get("technical_analysis"), dict) else {}
    pending_records = [
        r for r in (brackets.get("records") or []) if r.get("state") == "pending_buy"
    ]
    stale_snapshot = (
        build_pending_buy_stale_snapshot(
            mid=mid,
            operator_config=cfg,
            pending_records=pending_records,
        )
        if mid > 0
        else {"note": "mid unavailable — stale pending analysis skipped"}
    )
    scenario_hints = infer_scenario_hints(
        decision_reason=str(decision.get("reason") or ""),
        inventory=inv if isinstance(inv, dict) else {},
        reentry=reentry if isinstance(reentry, dict) else {},
        stale_snapshot=stale_snapshot if isinstance(stale_snapshot, dict) else {},
        opportunity_watch=hud_state.get("opportunity_watch") if isinstance(hud_state.get("opportunity_watch"), dict) else {},
        accumulation_regime=hud_state.get("accumulation_regime") if isinstance(hud_state.get("accumulation_regime"), dict) else {},
        reload_regime=hud_state.get("reload_regime") if isinstance(hud_state.get("reload_regime"), dict) else {},
    )
    operator_phase = normalize_operator_phase(cfg.get(OPERATOR_PHASE_KEY))
    market_regime = normalize_market_regime(cfg.get(OPERATOR_MARKET_REGIME_KEY))
    session_pnl = risk.get("session_pnl_xrp")
    try:
        session_pnl_f = float(session_pnl) if session_pnl is not None else None
    except (TypeError, ValueError):
        session_pnl_f = None
    realized_pnl = build_realized_pnl_snapshot(
        logs_dir="logs",
        hours=24.0,
        session_pnl_xrp=session_pnl_f,
    )

    lines = [
        build_operator_phase_context_block(operator_phase),
        "",
        build_market_regime_context_block(market_regime),
        "",
        format_realized_pnl_context_block(realized_pnl),
        "",
        "=== Alpha runtime snapshot ===",
        f"network={hud_state.get('network')} dry_run={hud_state.get('dry_run')} trading_enabled={hud_state.get('trading_enabled')}",
        f"paused={hud_state.get('operator_paused')} posture={hud_state.get('posture')} ready_state={hud_state.get('ready_state')}",
        f"mid={hud_state.get('mid')} portfolio_xrp_equiv={hud_state.get('portfolio_xrp_equiv')}",
        f"balances: XRP={hud_state.get('xrp')} RLUSD={hud_state.get('rlusd')}",
        "",
        "=== Inventory ===",
        f"xrp_ratio={inv.get('xrp_ratio')} target={inv.get('target_xrp_ratio')} deviation={inv.get('deviation')} label={inv.get('label')}",
        f"buy_blocked_imbalance={inv.get('buy_blocked')}",
        "",
        "=== Decision (latest cycle) ===",
        f"action={decision.get('action')} reason={decision.get('reason')} edge_pct={decision.get('edge_pct')}",
        "",
        build_gate_diagnostics_block(hud_state, bot_cfg),
        "",
        build_structure_context_block(structure, mid=mid),
        "",
        "=== Opportunity watch (operator readiness — NOT the same as posture) ===",
        json.dumps(hud_state.get("opportunity_watch") or {}, default=str)[:2000],
        "",
        build_accumulation_context_block(hud_state.get("accumulation_regime") or {}),
        "",
        build_reload_context_block(hud_state.get("reload_regime") or {}),
        "",
        "=== Momentum / tape (engine sub-signals) ===",
        json.dumps(
            {
                "momentum_entry": hud_state.get("momentum_entry"),
                "tape_participation": hud_state.get("tape_participation"),
            },
            default=str,
        )[:1500],
        "",
        "=== Risk ===",
        f"kill={risk.get('kill_switch_active')} drawdown_pct={risk.get('drawdown_pct')} session_pnl_xrp={risk.get('session_pnl_xrp')} (MTM only — see realized_bracket_pnl above)",
        f"trading_allowed={risk.get('trading_allowed')} preflight={risk.get('preflight_summary')}",
        f"alerts={risk.get('alerts')}",
        "",
        "=== Market conditions ===",
        json.dumps(mc, default=str)[:2500],
        "",
        _technical_analysis_context(ta),
        "",
        "=== Re-entry gate ===",
        json.dumps(reentry, default=str)[:1200],
        "",
        "=== Brackets ===",
        f"summary={json.dumps(brackets.get('summary'), default=str)}",
        f"open_records={json.dumps((brackets.get('records') or [])[:12], default=str)[:3000]}",
        "",
        "=== Pending buy stale diagnostics (for ladder / unfilled bid issues) ===",
        json.dumps(stale_snapshot, default=str)[:4000],
        "",
        "=== Scenario hints (auto from state — reference only, may not match operator intent) ===",
        f"likely_scenarios={scenario_hints or ['none']}",
        "",
        build_scenario_playbook(),
        "",
        build_skynet_knob_catalog(),
        "",
        "=== Open offers (sample) ===",
        json.dumps((hud_state.get("open_offers") or [])[:15], default=str)[:2000],
        "",
        "=== Operator knobs (effective) ===",
        json.dumps(cfg, default=str)[:3500],
        "",
        "=== Recent activity ===",
        json.dumps((hud_state.get("recent_activity") or [])[-15:], default=str)[:2000],
    ]
    return "\n".join(lines)


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty SKYNET advisor response")
    if raw.startswith("```"):
        parts = raw.split("```")
        for part in parts:
            chunk = part.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                raw = chunk
                break
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in SKYNET advisor response")
    return json.loads(raw[start : end + 1])


def parse_skynet_advisor_response(text: str) -> Dict[str, Any]:
    data = _extract_json_object(text)
    changes = data.get("suggested_changes")
    if changes is None:
        changes = []
    if not isinstance(changes, list):
        raise ValueError("suggested_changes must be a list")
    normalized: List[Dict[str, Any]] = []
    for item in changes:
        if not isinstance(item, dict):
            continue
        raw_key = str(item.get("key") or "").strip()
        if not raw_key:
            continue
        if raw_key in ("target_xrp_pct", "inventory_target_xrp_pct"):
            try:
                normalized.append(
                    {
                        "key": "inventory_target_xrp_ratio",
                        "value": float(item.get("value")) / 100.0,
                        "reason": str(item.get("reason") or ""),
                    }
                )
            except (TypeError, ValueError):
                continue
            continue
        key = normalize_suggestion_key(raw_key)
        normalized.append(
            {
                "key": key,
                "value": item.get("value"),
                "reason": str(item.get("reason") or ""),
            }
        )
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    return {
        "reasoning": str(data.get("reasoning") or ""),
        "summary": str(data.get("summary") or ""),
        "suggested_changes": normalized,
        "warnings": [str(w) for w in warnings],
    }


parse_grok_advisor_response = parse_skynet_advisor_response


def filter_applicable_suggestions(
    suggestions: List[Dict[str, Any]],
    *,
    base: BotConfig,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Return (sanitized_overrides, accepted_details, errors)."""
    patch: Dict[str, Any] = {}
    accepted: List[Dict[str, Any]] = []
    errors: List[str] = []

    for item in suggestions:
        raw_key = str(item.get("key") or "").strip()
        if not raw_key:
            continue
        key = normalize_suggestion_key(raw_key)
        if key in _BLOCKED_APPLY_KEYS:
            errors.append(f"{key}: blocked — change via dedicated HUD control")
            continue
        if key not in OPERATOR_TUNABLE_KEYS:
            errors.append(f"{raw_key}: not an operator tunable key")
            continue
        patch[key] = item.get("value")
        accepted.append({**item, "key": key})

    if not patch:
        return {}, [], errors

    sanitized, val_errors = validate_override_updates(patch, base=base)
    errors.extend(val_errors)
    if val_errors:
        return {}, [], errors

    final_accepted = [a for a in accepted if a["key"] in sanitized]
    return sanitized, final_accepted, errors


def call_skynet_advisor(
    *,
    user_prompt: str,
    context: str,
    api_key: str,
    model: str = "grok-3",
    timeout: int = 90,
    system_prompt: Optional[str] = None,
    user_message: Optional[str] = None,
    max_tokens: int = 4096,
    operator_phase: Optional[str] = None,
    market_regime: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    allowed = ", ".join(OPERATOR_TUNABLE_KEYS)
    system = system_prompt or _SYSTEM_PROMPT.format(allowed_keys=allowed)
    user_body = user_message
    if user_body is None:
        user_body = build_skynet_user_message(
            user_prompt=user_prompt,
            context=context,
            operator_phase=operator_phase,
            market_regime=market_regime,
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_body},
    ]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max(256, min(8192, int(max_tokens))),
        "temperature": 0.52,
    }
    resp = requests.post(_SKYNET_LLM_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    if not resp.ok:
        detail = resp.text[:500]
        raise RuntimeError(f"SKYNET advisor API {resp.status_code}: {detail}")
    message = resp.json().get("choices", [{}])[0].get("message", {}) or {}
    content = str(message.get("content") or "").strip()
    if not content:
        reasoning_trace = str(message.get("reasoning_content") or "").strip()
        if reasoning_trace:
            content = reasoning_trace
    if not content:
        refusal = str(message.get("refusal") or "").strip()
        if refusal:
            raise RuntimeError(f"SKYNET advisor refused: {refusal[:500]}")
        raise RuntimeError("SKYNET advisor returned empty content")
    parsed = parse_skynet_advisor_response(content)
    return content, parsed


call_grok_advisor = call_skynet_advisor


def format_advisor_display(parsed: Dict[str, Any]) -> str:
    lines = []
    if parsed.get("summary"):
        lines.append(parsed["summary"])
        lines.append("")
    if parsed.get("reasoning"):
        lines.append(parsed["reasoning"])
        lines.append("")
    changes = parsed.get("suggested_changes") or []
    if changes:
        lines.append("Suggested changes (Apply in HUD when applicable):")
        for c in changes:
            lines.append(f"  • {c.get('key')} → {c.get('value')} — {c.get('reason', '')}")
    warnings = parsed.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ⚠ {w}")
    return "\n".join(lines).strip()
