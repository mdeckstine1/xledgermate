"""Alpha SKYNET — Phase 1 Grok advisor (manual prompt + human-approved apply)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS, validate_override_updates
from config.settings import BotConfig
from utils.env_secrets import resolve_grok_key

logger = logging.getLogger(__name__)

_GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"

# Phase 1: never auto-apply mode switches without dedicated HUD confirmations.
_BLOCKED_APPLY_KEYS = frozenset({"dry_run"})

_SYSTEM_PROMPT = """You are SKYNET, an expert advisor for xLedgerMate Alpha — an XRPL XRP/RLUSD limit-order bag-growth bot.

You advise the human operator only. You do NOT execute trades. Be direct and practical.

Respond with a single JSON object (no markdown fences) using exactly this schema:
{{
  "reasoning": "<2-6 sentences explaining current state and your analysis>",
  "summary": "<one-line headline for the operator>",
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
- Explain HOLD reasons using inventory deviation, edge gates, re-entry cooldowns, TA, depth, and max_pending_buys.
"""


def skynet_status(config: BotConfig | None = None) -> Dict[str, Any]:
    cfg = config or BotConfig.load()
    key = resolve_grok_key(getattr(cfg, "alpha_grok_api_key", "") or "")
    model = (getattr(cfg, "alpha_skynet_grok_model", None) or "grok-3").strip() or "grok-3"
    max_tokens = int(getattr(cfg, "alpha_skynet_grok_max_tokens", 4096) or 4096)
    enabled = bool(getattr(cfg, "alpha_skynet_enabled", True))
    return {
        "enabled": enabled,
        "configured": bool(key),
        "model": model,
        "max_tokens": max(256, min(8192, max_tokens)),
        "key_hint": f"xai-…{key[-4:]}" if len(key) >= 8 else "",
    }


def build_skynet_context(
    hud_state: Dict[str, Any],
    *,
    operator_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Serialize rich operator context for Grok."""
    inv = hud_state.get("inventory") or {}
    risk = hud_state.get("risk") or {}
    decision = hud_state.get("decision") or {}
    mc = hud_state.get("market_conditions") or {}
    ta = hud_state.get("technical_analysis") or {}
    brackets = hud_state.get("brackets") or {}
    reentry = hud_state.get("reentry") or {}
    cfg = operator_config or hud_state.get("config_effective") or {}

    lines = [
        "=== Alpha runtime snapshot ===",
        f"network={hud_state.get('network')} dry_run={hud_state.get('dry_run')} trading_enabled={hud_state.get('trading_enabled')}",
        f"paused={hud_state.get('operator_paused')} posture={hud_state.get('posture')}",
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
        "=== Risk ===",
        f"kill={risk.get('kill_switch_active')} drawdown_pct={risk.get('drawdown_pct')} session_pnl_xrp={risk.get('session_pnl_xrp')}",
        f"trading_allowed={risk.get('trading_allowed')} preflight={risk.get('preflight_summary')}",
        f"alerts={risk.get('alerts')}",
        "",
        "=== Market conditions ===",
        json.dumps(mc, default=str)[:2500],
        "",
        "=== Technical analysis ===",
        json.dumps(
            {
                k: ta.get(k)
                for k in (
                    "enabled",
                    "bias",
                    "buy_score",
                    "sell_score",
                    "breakout_score",
                    "buy_gate",
                    "sell_gate",
                    "summary",
                )
                if ta.get(k) is not None
            },
            default=str,
        ),
        "",
        "=== Re-entry gate ===",
        json.dumps(reentry, default=str)[:1200],
        "",
        "=== Brackets ===",
        f"summary={json.dumps(brackets.get('summary'), default=str)}",
        f"open_records={json.dumps((brackets.get('records') or [])[:12], default=str)[:3000]}",
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
        raise ValueError("empty Grok response")
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
        raise ValueError("no JSON object in Grok response")
    return json.loads(raw[start : end + 1])


def parse_grok_advisor_response(text: str) -> Dict[str, Any]:
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
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if key == "target_xrp_pct":
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
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if key in _BLOCKED_APPLY_KEYS:
            errors.append(f"{key}: blocked — change via dedicated HUD control")
            continue
        if key not in OPERATOR_TUNABLE_KEYS:
            errors.append(f"{key}: not an operator tunable key")
            continue
        patch[key] = item.get("value")
        accepted.append(item)

    if not patch:
        return {}, [], errors

    sanitized, val_errors = validate_override_updates(patch, base=base)
    errors.extend(val_errors)
    if val_errors:
        return {}, [], errors

    final_accepted = [a for a in accepted if a["key"] in sanitized]
    return sanitized, final_accepted, errors


def call_grok_advisor(
    *,
    user_prompt: str,
    context: str,
    api_key: str,
    model: str = "grok-3",
    timeout: int = 90,
    system_prompt: Optional[str] = None,
    user_message: Optional[str] = None,
    max_tokens: int = 4096,
) -> Tuple[str, Dict[str, Any]]:
    allowed = ", ".join(OPERATOR_TUNABLE_KEYS)
    system = system_prompt or _SYSTEM_PROMPT.format(allowed_keys=allowed)
    user_body = user_message
    if user_body is None:
        user_body = f"Context:\n{context}\n\n---\n\nOperator prompt:\n{user_prompt.strip()}"
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
        "temperature": 0.35,
    }
    resp = requests.post(_GROK_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    if not resp.ok:
        detail = resp.text[:500]
        raise RuntimeError(f"Grok API {resp.status_code}: {detail}")
    message = resp.json().get("choices", [{}])[0].get("message", {}) or {}
    content = str(message.get("content") or "").strip()
    if not content:
        reasoning_trace = str(message.get("reasoning_content") or "").strip()
        if reasoning_trace:
            content = reasoning_trace
    if not content:
        refusal = str(message.get("refusal") or "").strip()
        if refusal:
            raise RuntimeError(f"Grok refused: {refusal[:500]}")
        raise RuntimeError("Grok returned empty content")
    parsed = parse_grok_advisor_response(content)
    return content, parsed


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
        lines.append("Suggested changes:")
        for c in changes:
            lines.append(f"  • {c.get('key')} → {c.get('value')} — {c.get('reason', '')}")
    warnings = parsed.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ⚠ {w}")
    return "\n".join(lines).strip()
