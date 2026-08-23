"""Alpha SKYNET Phase 2/3 — bounded advisor agent with optional supervised autonomy."""

from __future__ import annotations

import json
import logging
import random
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alpha.hud.skynet import (
    build_skynet_context,
    call_skynet_advisor,
    filter_applicable_suggestions,
    format_advisor_display,
    parse_skynet_advisor_response,
)
from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS, apply_overrides, effective_config_snapshot
from config.settings import BotConfig
from utils.env_secrets import resolve_grok_key

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_PATH = Path("logs/alpha_skynet_agent.json")
_RUNTIME_PATH = Path("logs/alpha_runtime_state.json")
_AUDIT_PATH = Path("logs/alpha_skynet_audit.jsonl")
_AGENT_LOCK = threading.Lock()
_FULL_MODE_CONFIRM = "ENABLE_FULL_SKYNET"

_COOLDOWN_GUARD_KEYS = (
    "alpha_reentry_tp_cooldown_cycles",
    "alpha_reentry_tp_cooldown_minutes",
    "alpha_reentry_sl_cooldown_cycles",
    "alpha_reentry_sl_cooldown_minutes",
)

# Guardrails aligned with Maximize / bag-growth accumulation (not pure MM).
_DEFAULT_GUARDRAILS: Dict[str, Any] = {
    "alpha_risk_per_trade_pct": {"min": 2.0, "max": 4.0},
    "inventory_target_xrp_pct": {"min": 75.0, "max": 90.0},
    "alpha_ta_weight": {"min": 0.4, "max": 0.85},
    "alpha_strength_deviation": {"min": 0.03, "max": 0.10},
    "alpha_weakness_deviation": {"min": 0.02, "max": 0.08},
    "alpha_buy_limit_offset_pct": {"min": 0.08, "max": 0.25},
    "alpha_sell_limit_offset_pct": {"min": 0.05, "max": 0.18},
    "alpha_max_pending_buys": {"min": 1, "max": 4},
    "alpha_max_pending_sells": {"min": 1, "max": 3},
    "alpha_accumulation_max_deviation": {"min": 0.08, "max": 0.15},
    "alpha_bull_run_max_deviation": {"min": 0.08, "max": 0.15},
    "alpha_reload_min_rlusd_deploy_xrp_equiv": {"min": 25.0, "max": 80.0},
    "alpha_ta_min_buy_score": {"min": 1.0, "max": 3.5},
    "alpha_ta_min_sell_score": {"min": 1.0, "max": 3.5},
    "initial_stop_loss_pct": {"min": 0.05, "max": 0.12},
    "alpha_reentry_tp_cooldown_cycles": {"min": 0, "max": 30},
    "alpha_reentry_tp_cooldown_minutes": {"min": 0.0, "max": 180.0},
    "alpha_reentry_sl_cooldown_cycles": {"min": 0, "max": 60},
    "alpha_reentry_sl_cooldown_minutes": {"min": 0.0, "max": 480.0},
    "alpha_drawdown_reload_stage1_arm_pct": {"min": 1.5, "max": 5.0},
    "alpha_drawdown_reload_stage2_arm_pct": {"min": 3.0, "max": 8.0},
    "alpha_drawdown_reload_total_bag_pct": {"min": 2.0, "max": 8.0},
    "alpha_drawdown_reload_stage1_bag_pct": {"min": 1.0, "max": 4.0},
    "alpha_drawdown_reload_stage2_bag_pct": {"min": 1.0, "max": 4.0},
    "max_changes_per_cycle": 2,
}

# Core-bag Maximize: never re-enable SL factory via agent.
_FORBIDDEN_TRUE_KEYS = frozenset(
    {
        "alpha_brackets_enabled",
        "bracket_trailing_enabled",
        "alpha_reload_block_accumulation_until_funded",
    }
)

_DEFAULT_EMERGENCY_RULES: Dict[str, Any] = {
    "enabled": True,
    "drawdown_pause_pct": 8.0,
    "session_loss_pause_xrp": 25.0,
}

# Event-driven agent runs (token saver: decision_changed OFF by default — too chatty).
_DEFAULT_EVENT_TRIGGERS: Dict[str, Any] = {
    "enabled": True,
    # After an event-driven run, ignore further events for this many cycles (scheduled still OK).
    "min_cycles_between_event_runs": 12,
    "kill_switch": True,
    "drawdown_spike": True,
    "drawdown_spike_pct": 1.0,
    "session_loss": True,
    "session_loss_xrp": 8.0,
    "inventory_shift": True,
    "inventory_shift_dev": 0.12,
    "decision_changed": False,
    "opportunity": False,
    "accumulation": True,
    "reload": True,
    "drawdown_reload": True,
    # Free sell slots / powder — high value for Maximize autonomy.
    "sell_slot_stall": True,
    "powder_shortfall": True,
}

_AGENT_SYSTEM_PROMPT = """You are Agent Smith (SKYNET Phase 2) for xLedgerMate Alpha — a bounded advisor for an XRPL XRP/RLUSD **accumulation / bag-growth** bot (Maximize doctrine).

This is NOT pure market-making. Core loop:
  powder floor (RLUSD) → buy dips/weakness/breakouts into core bag → hold → inventory_trim/harvest when heavy → refill powder → repeat.
Core bag has brackets OFF (no TP/SL factory). Clip size scales with portfolio (risk_per_trade_pct).

Voice: plain English, conversational, light dry humor OK — still output strict JSON only.
Suggest operator knob changes ONLY when they improve long-term XRP bag growth while respecting risk and Maximize doctrine.

Respond with a single JSON object (no markdown fences):
{{
  "reasoning": "<3-8 sentences: inventory vs target, powder/reload, decision/HOLD reason, TA, harvest/dip/accum — not MM language>",
  "summary": "<one-line headline>",
  "suggested_changes": [
    {{"key": "<operator_config_key>", "value": <json_value>, "reason": "<why this knob, tied to current state>"}}
  ],
  "warnings": ["<optional safety warnings>"]
}}

Hard rules:
- Only keys from this allowlist: {allowed_keys}
- NEVER suggest dry_run changes.
- NEVER re-enable alpha_brackets_enabled or bracket_trailing_enabled (must stay false for core bag).
- NEVER set alpha_reload_block_accumulation_until_funded to true (Maximize keeps residual bids possible).
- NEVER exceed these guardrails (values must stay inside min/max):
{guardrail_lines}
- Suggest at most {max_changes} change(s) per response.
- inventory_target_xrp_ratio is 0.0-1.0 (not percent). Prefer inventory_target_xrp_ratio over target_xrp_pct. Keep target roughly 80–90% bag bias (Maximize ~85%).
- Prefer empty suggested_changes when HOLD is inventory_trim / heavy_prefer_trim waiting for near-market fills — that is healthy rebalance.
- If HOLD is max_pending_sells for many cycles with asks far above mid, prefer enabling/tightening stale sell drift (alpha_stale_pending_sell_*) rather than raising max_pending_sells.
- When heavy (dev above strength): do NOT loosen buy offsets to chase; trims/harvest first.
- Prefer grind-friendly harvest/dip arms (~1.5–2.5% 24h) over 3.5%+ shock-only arms for autonomous Maximize.
- When powder below reload floor: favor funding/sell readiness, not more bids.
- When powder OK and light/dip-ready: modest deployment knobs (pending buys, buy offset, ta_min_buy) — scale phase, not trust panic.
- session_pnl_xrp is MTM — not realized edge. Use bag_growth bot-adjusted and realized_bracket_pnl.
- Pending buys are passive limit bids. Ladder clutter → drift/max_pending; entry churn → widen drift (Scenario G).
- Small incremental adjustments only — no reckless risk increases.
"""

_AGENT_USER_PROMPT = """Autonomous agent review (Phase 2 — Maximize accumulation soak).

Analyze runtime context. Only suggest knobs if they clearly help bag growth without fighting Maximize
(target ~85%, powder floor, core bag no brackets, heavy→trim, light→dip buy).
If HOLD is correct (waiting on sell fills, quiet near target, TA correctly blocking), return empty suggested_changes.

Context:
{context}
"""

_FULL_MODE_SYSTEM_PROMPT = """You are SKYNET Full Mode for xLedgerMate Alpha — Maximize accumulation / bag-growth on XRPL XRP/RLUSD.

Mandate: long-term XRP stack growth with powder discipline. NOT pure MM. Core bag brackets OFF.
Loop: fund RLUSD floor → buy dips into bag → hold → trim when heavy / harvest rips → refill powder.

Respond with a single JSON object (no markdown fences):
{{
  "reasoning": "<4-10 sentences: deviation vs target, powder/reload, decision reason, TA, harvest/dip>",
  "summary": "<one-line headline>",
  "suggested_changes": [
    {{"key": "<operator_config_key>", "value": <json_value>, "reason": "<why>"}}
  ],
  "warnings": ["<optional>"]
}}

Discipline:
- Capital preservation after losses — conservative, not reactive.
- Never re-enable brackets / trailing / reload-block-until-funded.
- Never chase buys while inventory is heavy; prefer trim path.
- Empty suggested_changes is often correct during soak.
- NEVER dry_run. NEVER exceed guardrails.
- inventory_target_xrp_ratio is 0.0-1.0. Keep bag bias ~80–90%.

Allowlist only: {allowed_keys}

Guardrails (min/max — stay inside):
{guardrail_lines}

Max {max_changes} change(s) per response.
"""

_FULL_MODE_USER_PROMPT = """Full SKYNET review (Maximize accumulation). Analyze context.
Only suggest bounded knobs that improve bag growth without undoing Maximize posture.
If HOLD is correct, say so and return empty suggested_changes.

Context:
{context}
"""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def default_agent_config() -> Dict[str, Any]:
    return {
        "agent_enabled": False,
        "full_mode_enabled": False,
        # Token-saver soak: ~10–15 min between scheduled runs at 15s cycles.
        "interval_cycles_min": 40,
        "interval_cycles_max": 60,
        # Max auto Grok calls per UTC day (0 = unlimited). Manual force can bypass when empty.
        "daily_call_budget": 48,
        "daily_calls_used": 0,
        "budget_day_utc": None,
        # Agent response budget (manual Ask SKYNET keeps config alpha_skynet_grok_max_tokens).
        "max_tokens": 1536,
        "guardrails": deepcopy(_DEFAULT_GUARDRAILS),
        "emergency_rules": deepcopy(_DEFAULT_EMERGENCY_RULES),
        "event_triggers": deepcopy(_DEFAULT_EVENT_TRIGGERS),
        "last_run_engine_cycle": 0,
        "next_run_engine_cycle": 0,
        "last_event_run_engine_cycle": 0,
        "last_run_utc": None,
        "running": False,
        "latest_proposal": None,
        "last_event_snapshot": None,
    }


def _normalize_event_triggers(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(_DEFAULT_EVENT_TRIGGERS)
    if not isinstance(raw, dict):
        return out
    for key, default in _DEFAULT_EVENT_TRIGGERS.items():
        if key not in raw:
            continue
        val = raw[key]
        if isinstance(default, bool):
            out[key] = bool(val)
        else:
            try:
                if key.endswith("_pct") or key.endswith("_dev") or key.endswith("_xrp"):
                    out[key] = float(val)
                else:
                    out[key] = int(val)
            except (TypeError, ValueError):
                pass
    out["min_cycles_between_event_runs"] = max(
        0, min(500, int(out.get("min_cycles_between_event_runs") or 0))
    )
    out["drawdown_spike_pct"] = max(0.25, min(20.0, float(out.get("drawdown_spike_pct") or 1.0)))
    out["session_loss_xrp"] = max(0.5, min(500.0, float(out.get("session_loss_xrp") or 8.0)))
    out["inventory_shift_dev"] = max(0.02, min(0.5, float(out.get("inventory_shift_dev") or 0.12)))
    return out


def _utc_day() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def refresh_daily_budget(agent: Dict[str, Any]) -> Dict[str, Any]:
    """Roll daily call counter at UTC midnight."""
    today = _utc_day()
    stored = str(agent.get("budget_day_utc") or "")
    if stored != today:
        # New calendar day → reset. First stamp (empty stored) keeps existing counter.
        agent["budget_day_utc"] = today
        if stored:
            agent["daily_calls_used"] = 0
        else:
            agent["daily_calls_used"] = int(agent.get("daily_calls_used") or 0)
    return agent


def budget_remaining(agent: Dict[str, Any]) -> Optional[int]:
    """None = unlimited; else remaining auto calls today."""
    refresh_daily_budget(agent)
    budget = int(agent.get("daily_call_budget") or 0)
    if budget <= 0:
        return None
    used = int(agent.get("daily_calls_used") or 0)
    return max(0, budget - used)


def budget_allows_run(agent: Dict[str, Any], *, force: bool = False) -> Tuple[bool, str]:
    """Whether a Grok call is allowed. force=True bypasses empty budget (manual trigger)."""
    refresh_daily_budget(agent)
    remaining = budget_remaining(agent)
    if remaining is None:
        return True, "unlimited"
    if remaining > 0:
        return True, f"remaining={remaining}"
    if force:
        return True, "budget_exhausted_force_bypass"
    return False, "daily_call_budget_exhausted"


def record_budget_call(agent: Dict[str, Any]) -> None:
    refresh_daily_budget(agent)
    agent["daily_calls_used"] = int(agent.get("daily_calls_used") or 0) + 1


def load_agent_config(path: Path = _DEFAULT_AGENT_PATH) -> Dict[str, Any]:
    cfg = default_agent_config()
    if not path.is_file():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    for key in (
        "agent_enabled",
        "full_mode_enabled",
        "interval_cycles_min",
        "interval_cycles_max",
        "daily_call_budget",
        "daily_calls_used",
        "budget_day_utc",
        "max_tokens",
        "last_event_run_engine_cycle",
    ):
        if key in data:
            cfg[key] = data[key]
    if isinstance(data.get("emergency_rules"), dict):
        merged_er = deepcopy(_DEFAULT_EMERGENCY_RULES)
        merged_er.update(data["emergency_rules"])
        cfg["emergency_rules"] = _normalize_emergency_rules(merged_er)
    if isinstance(data.get("guardrails"), dict):
        merged = deepcopy(_DEFAULT_GUARDRAILS)
        merged.update(data["guardrails"])
        cfg["guardrails"] = _normalize_guardrails(merged)
    if isinstance(data.get("event_triggers"), dict):
        cfg["event_triggers"] = _normalize_event_triggers(data["event_triggers"])
    for key in (
        "last_run_engine_cycle",
        "next_run_engine_cycle",
        "last_run_utc",
        "running",
        "latest_proposal",
        "last_event_snapshot",
    ):
        if key in data:
            cfg[key] = data[key]
    refresh_daily_budget(cfg)
    return cfg


def save_agent_config(config: Dict[str, Any], path: Path = _DEFAULT_AGENT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _normalize_emergency_rules(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(_DEFAULT_EMERGENCY_RULES)
    if "enabled" in raw:
        out["enabled"] = bool(raw["enabled"])
    for key in ("drawdown_pause_pct", "session_loss_pause_xrp"):
        if key in raw and raw[key] is not None:
            try:
                out[key] = float(raw[key])
            except (TypeError, ValueError):
                pass
    if out.get("drawdown_pause_pct") is not None:
        out["drawdown_pause_pct"] = max(0.5, min(50.0, float(out["drawdown_pause_pct"])))
    if out.get("session_loss_pause_xrp") is not None:
        out["session_loss_pause_xrp"] = max(0.0, float(out["session_loss_pause_xrp"]))
    return out


def _normalize_guardrails(raw: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(_DEFAULT_GUARDRAILS)
    for key, bounds in raw.items():
        if key == "max_changes_per_cycle":
            try:
                out[key] = max(0, min(10, int(bounds)))
            except (TypeError, ValueError):
                pass
            continue
        if not isinstance(bounds, dict):
            continue
        base = out.get(key, {})
        if not isinstance(base, dict):
            base = {}
        merged = dict(base)
        if "min" in bounds:
            merged["min"] = bounds["min"]
        if "max" in bounds:
            merged["max"] = bounds["max"]
        out[key] = merged
    return out


def _guardrails_equal(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def merge_agent_patch(
    patch: Dict[str, Any],
    path: Path = _DEFAULT_AGENT_PATH,
) -> Tuple[Dict[str, Any], List[str]]:
    """Merge HUD patch into agent config; return (config, errors)."""
    current = load_agent_config(path)
    errors: List[str] = []

    if "agent_enabled" in patch:
        current["agent_enabled"] = bool(patch["agent_enabled"])
        if not current["agent_enabled"]:
            current["full_mode_enabled"] = False

    if "full_mode_enabled" in patch:
        want_full = bool(patch["full_mode_enabled"])
        if want_full:
            if patch.get("confirm") != _FULL_MODE_CONFIRM:
                errors.append(f'confirm "{_FULL_MODE_CONFIRM}" required to enable full SKYNET mode')
            elif not (current.get("agent_enabled") or patch.get("agent_enabled")):
                errors.append("agent_enabled must be true for full SKYNET mode")
            else:
                current["full_mode_enabled"] = True
                current["agent_enabled"] = True
        else:
            current["full_mode_enabled"] = False

    if "emergency_rules" in patch and isinstance(patch["emergency_rules"], dict):
        merged_er = deepcopy(current.get("emergency_rules") or _DEFAULT_EMERGENCY_RULES)
        merged_er.update(patch["emergency_rules"])
        current["emergency_rules"] = _normalize_emergency_rules(merged_er)

    for key in ("interval_cycles_min", "interval_cycles_max"):
        if key in patch:
            try:
                val = int(patch[key])
                if val < 1:
                    raise ValueError("must be >= 1")
                if val > 500:
                    raise ValueError("must be <= 500")
                current[key] = val
            except (TypeError, ValueError) as exc:
                errors.append(f"{key}: {exc}")

    if current["interval_cycles_min"] > current["interval_cycles_max"]:
        errors.append("interval_cycles_min cannot exceed interval_cycles_max")

    if "daily_call_budget" in patch:
        try:
            val = int(patch["daily_call_budget"])
            if val < 0:
                raise ValueError("must be >= 0 (0=unlimited)")
            current["daily_call_budget"] = min(10000, val)
        except (TypeError, ValueError) as exc:
            errors.append(f"daily_call_budget: {exc}")

    if "max_tokens" in patch:
        try:
            val = int(patch["max_tokens"])
            if val < 256:
                raise ValueError("must be >= 256")
            current["max_tokens"] = max(256, min(8192, val))
        except (TypeError, ValueError) as exc:
            errors.append(f"max_tokens: {exc}")

    if "event_triggers" in patch and isinstance(patch["event_triggers"], dict):
        merged_ev = deepcopy(current.get("event_triggers") or _DEFAULT_EVENT_TRIGGERS)
        merged_ev.update(patch["event_triggers"])
        current["event_triggers"] = _normalize_event_triggers(merged_ev)

    if "guardrails" in patch and isinstance(patch["guardrails"], dict):
        prior = _normalize_guardrails(current.get("guardrails") or _DEFAULT_GUARDRAILS)
        merged = deepcopy(current.get("guardrails") or _DEFAULT_GUARDRAILS)
        merged.update(patch["guardrails"])
        current["guardrails"] = _normalize_guardrails(merged)
        if not _guardrails_equal(current["guardrails"], prior):
            current["latest_proposal"] = None

    if errors:
        return current, errors
    save_agent_config(current, path)
    return current, []


def _load_hud_state(path: Path = _RUNTIME_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _guardrail_bounds(guardrails: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    if key in guardrails and isinstance(guardrails[key], dict):
        return guardrails[key]
    if key == "inventory_target_xrp_ratio":
        return guardrails.get("inventory_target_xrp_pct")
    return None


def _value_in_guardrail(key: str, value: Any, guardrails: Dict[str, Any]) -> Tuple[bool, str]:
    bounds = _guardrail_bounds(guardrails, key)
    if not bounds:
        return True, ""

    try:
        if key == "inventory_target_xrp_ratio":
            num = float(value) * 100.0
        elif key in _COOLDOWN_GUARD_KEYS and key.endswith("_cycles"):
            num = int(value)
        else:
            num = float(value)
    except (TypeError, ValueError):
        return False, f"{key}: not a number"

    lo = bounds.get("min")
    hi = bounds.get("max")
    if lo is not None and num < float(lo):
        return False, f"{key}={num} below guardrail min {lo}"
    if hi is not None and num > float(hi):
        return False, f"{key}={num} above guardrail max {hi}"
    return True, ""


def filter_guardrailed_suggestions(
    suggestions: List[Dict[str, Any]],
    *,
    guardrails: Dict[str, Any],
    base: BotConfig,
    current_effective: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Return (safe_changes, rejected_changes, errors)."""
    max_changes = int(guardrails.get("max_changes_per_cycle", 2) or 2)
    max_changes = max(0, min(10, max_changes))

    sanitized, accepted, val_errors = filter_applicable_suggestions(suggestions, base=base)
    if val_errors and not accepted:
        return [], [], val_errors

    effective = current_effective or effective_config_snapshot(
        apply_overrides(base, {}),
    )

    safe: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    errors = list(val_errors)

    for item in accepted:
        key = item["key"]
        # Maximize core-bag: reject re-enabling brackets / hard accum block.
        if key in _FORBIDDEN_TRUE_KEYS and bool(item.get("value")):
            msg = f"{key}: forbidden true under Maximize core-bag doctrine"
            rejected.append({**item, "reject_reason": msg})
            errors.append(msg)
            continue
        ok, msg = _value_in_guardrail(key, item.get("value"), guardrails)
        if not ok:
            rejected.append({**item, "reject_reason": msg})
            errors.append(msg)
            continue
        if len(safe) >= max_changes:
            rejected.append(
                {
                    **item,
                    "reject_reason": f"max_changes_per_cycle={max_changes}",
                }
            )
            errors.append(f"{key}: exceeds max changes per cycle ({max_changes})")
            continue
        enriched = dict(item)
        enriched["description"] = describe_knob_change(
            key,
            effective.get(key),
            item.get("value"),
        )
        safe.append(enriched)

    return safe, rejected, errors


def describe_knob_change(key: str, old_raw: Any, new_raw: Any) -> str:
    label = key
    if key == "inventory_target_xrp_ratio":
        label = "target_xrp_pct"
        try:
            old_v = round(float(old_raw) * 100.0, 1)
            new_v = round(float(new_raw) * 100.0, 1)
        except (TypeError, ValueError):
            old_v, new_v = old_raw, new_raw
    else:
        old_v, new_v = old_raw, new_raw
        try:
            if isinstance(old_raw, (int, float)) or isinstance(new_raw, (int, float)):
                old_v = round(float(old_raw), 4) if old_raw is not None else "?"
                new_v = round(float(new_raw), 4)
        except (TypeError, ValueError):
            pass

    if old_v == new_v:
        return f"set {label} to {new_v}"
    try:
        if float(new_v) > float(old_v):
            verb = "raise"
        elif float(new_v) < float(old_v):
            verb = "lower"
        else:
            verb = "set"
    except (TypeError, ValueError):
        verb = "set"
    return f"{verb} {label} from {old_v} to {new_v}"


def format_agent_proposal_display(
    parsed: Dict[str, Any],
    *,
    safe_changes: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    source: str = "agent",
) -> str:
    lines = [f"[SKYNET {source}]"]
    if parsed.get("summary"):
        lines.append(parsed["summary"])
        lines.append("")
    if parsed.get("reasoning"):
        lines.append(parsed["reasoning"])
        lines.append("")
    if safe_changes:
        lines.append("Safe changes (within guardrails):")
        for c in safe_changes:
            desc = c.get("description") or f"{c.get('key')} → {c.get('value')}"
            reason = c.get("reason") or ""
            lines.append(f"  • {desc}")
            if reason:
                lines.append(f"      {reason}")
    else:
        lines.append("No safe changes within guardrails.")
    if rejected:
        lines.append("")
        lines.append("Rejected / out of guardrails:")
        for c in rejected:
            lines.append(f"  ✗ {c.get('key')} → {c.get('value')} — {c.get('reject_reason', '')}")
    warnings = parsed.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ⚠ {w}")
    return "\n".join(lines).strip()


def _guardrail_prompt_lines(guardrails: Dict[str, Any]) -> str:
    preferred = (
        "alpha_risk_per_trade_pct",
        "inventory_target_xrp_pct",
        "alpha_ta_weight",
        "alpha_strength_deviation",
        "alpha_weakness_deviation",
        "alpha_buy_limit_offset_pct",
        "alpha_sell_limit_offset_pct",
        "alpha_max_pending_buys",
        "alpha_max_pending_sells",
        "alpha_reload_min_rlusd_deploy_xrp_equiv",
        "alpha_ta_min_buy_score",
        "alpha_ta_min_sell_score",
        "alpha_accumulation_max_deviation",
        "alpha_bull_run_max_deviation",
        *_COOLDOWN_GUARD_KEYS,
        "alpha_drawdown_reload_stage1_arm_pct",
        "alpha_drawdown_reload_stage2_arm_pct",
        "alpha_drawdown_reload_total_bag_pct",
    )
    lines = []
    seen = set()
    for key in preferred:
        bounds = guardrails.get(key)
        if isinstance(bounds, dict) and ("min" in bounds or "max" in bounds):
            lines.append(f"- {key}: min={bounds.get('min')} max={bounds.get('max')}")
            seen.add(key)
    for key, bounds in guardrails.items():
        if key in seen or key == "max_changes_per_cycle":
            continue
        if isinstance(bounds, dict) and ("min" in bounds or "max" in bounds):
            lines.append(f"- {key}: min={bounds.get('min')} max={bounds.get('max')}")
    lines.append("- alpha_brackets_enabled: must stay false (core bag)")
    lines.append("- bracket_trailing_enabled: must stay false")
    lines.append("- alpha_reload_block_accumulation_until_funded: must stay false")
    return "\n".join(lines)


def append_audit_entry(entry: Dict[str, Any], path: Path = _AUDIT_PATH) -> None:
    """Append one JSON audit line for every SKYNET decision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _utc_now(), **entry}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def load_audit_entries(*, limit: int = 50, path: Path = _AUDIT_PATH) -> List[Dict[str, Any]]:
    if not path.is_file() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in reversed(lines[-max(limit * 2, limit) :]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def _event_snapshot(hud_state: Dict[str, Any]) -> Dict[str, Any]:
    risk = hud_state.get("risk") or {}
    inv = hud_state.get("inventory") or {}
    decision = hud_state.get("decision") or {}
    reason = str(decision.get("reason") or "")
    return {
        "engine_cycle": int(hud_state.get("engine_cycle") or 0),
        "decision_action": str(decision.get("action") or ""),
        "decision_reason": reason[:160],
        "sell_slot_stall": "max_pending_sells" in reason,
        "kill_switch_active": bool(risk.get("kill_switch_active")),
        "drawdown_pct": float(risk.get("drawdown_pct") or 0.0),
        "session_pnl_xrp": float(risk.get("session_pnl_xrp") or 0.0),
        "inventory_deviation": float(inv.get("deviation") or 0.0),
        "trading_enabled": hud_state.get("trading_enabled"),
        "ready_state": hud_state.get("ready_state"),
        "opportunity_headline": (hud_state.get("opportunity_watch") or {}).get("headline"),
        "accumulation_phase": (hud_state.get("accumulation_regime") or {}).get("phase"),
        "accumulation_armed": (hud_state.get("accumulation_regime") or {}).get("armed"),
        "accumulation_missed": (hud_state.get("accumulation_regime") or {})
        .get("scorecard", {})
        .get("missed_opportunity"),
        "reload_phase": (hud_state.get("reload_regime") or {}).get("phase"),
        "reload_blocks_accumulation": (hud_state.get("reload_regime") or {}).get(
            "blocks_accumulation"
        ),
        "drawdown_phase": (hud_state.get("drawdown_reload") or {}).get("phase"),
        "drawdown_armed": (hud_state.get("drawdown_reload") or {}).get("armed"),
        "portfolio_xrp_equiv": (hud_state.get("bag_growth") or {}).get("portfolio_xrp_equiv")
        or hud_state.get("portfolio_xrp_equiv"),
    }


def detect_significant_events(
    hud_state: Dict[str, Any],
    last_snapshot: Optional[Dict[str, Any]],
    event_policy: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Return (triggered, reasons) for event-driven agent runs (policy-gated)."""
    if not hud_state:
        return False, []
    policy = _normalize_event_triggers(event_policy or _DEFAULT_EVENT_TRIGGERS)
    if not policy.get("enabled", True):
        return False, []
    snap = _event_snapshot(hud_state)
    if not last_snapshot:
        return False, []

    reasons: List[str] = []
    if policy.get("kill_switch") and snap["kill_switch_active"] and not last_snapshot.get(
        "kill_switch_active"
    ):
        reasons.append("kill_switch_activated")
    if (
        policy.get("decision_changed")
        and snap["decision_action"]
        and snap["decision_action"] != last_snapshot.get("decision_action")
    ):
        reasons.append(
            f"decision_changed:{last_snapshot.get('decision_action')}→{snap['decision_action']}"
        )
    dd_spike = float(policy.get("drawdown_spike_pct") or 1.0)
    dd_delta = snap["drawdown_pct"] - float(last_snapshot.get("drawdown_pct") or 0.0)
    if policy.get("drawdown_spike") and dd_delta >= dd_spike:
        reasons.append(f"drawdown_spike:+{dd_delta:.2f}pct")
    loss_thr = float(policy.get("session_loss_xrp") or 8.0)
    pnl_delta = snap["session_pnl_xrp"] - float(last_snapshot.get("session_pnl_xrp") or 0.0)
    if policy.get("session_loss") and pnl_delta <= -loss_thr:
        reasons.append(f"session_loss:{pnl_delta:.2f}xrp")
    inv_thr = float(policy.get("inventory_shift_dev") or 0.12)
    dev_delta = abs(
        snap["inventory_deviation"] - float(last_snapshot.get("inventory_deviation") or 0.0)
    )
    if policy.get("inventory_shift") and dev_delta >= inv_thr:
        reasons.append(f"inventory_shift:deviation_delta={dev_delta:.3f}")

    if policy.get("opportunity"):
        rs = snap.get("ready_state")
        prev_rs = last_snapshot.get("ready_state")
        if rs and rs != prev_rs and rs in ("armed", "blocked", "watching", "executing"):
            reasons.append(f"opportunity_{rs}")
        if rs == "blocked" and prev_rs in ("watching", "armed", None, "idle"):
            reasons.append("opportunity_blocked_on_rip")

    if policy.get("accumulation"):
        acc_phase = snap.get("accumulation_phase")
        prev_acc = last_snapshot.get("accumulation_phase")
        if (
            acc_phase
            and acc_phase != prev_acc
            and acc_phase in ("armed", "executing", "blocked", "primed")
        ):
            reasons.append(f"accumulation_{acc_phase}")
        if snap.get("accumulation_armed") and not last_snapshot.get("accumulation_armed"):
            reasons.append("accumulation_armed")

    if policy.get("reload"):
        if snap.get("reload_blocks_accumulation") and not last_snapshot.get(
            "reload_blocks_accumulation"
        ):
            reasons.append("reload_blocks_accumulation")
        if snap.get("reload_phase") == "armed" and last_snapshot.get("reload_phase") != "armed":
            reasons.append("reload_armed")

    if policy.get("drawdown_reload"):
        if snap.get("drawdown_armed") and not last_snapshot.get("drawdown_armed"):
            reasons.append("drawdown_armed")
        if snap.get("drawdown_phase") == "armed" and last_snapshot.get("drawdown_phase") != "armed":
            reasons.append("drawdown_phase_armed")

    if policy.get("sell_slot_stall"):
        if snap.get("sell_slot_stall") and not last_snapshot.get("sell_slot_stall"):
            reasons.append("sell_slot_stall:max_pending_sells")

    if policy.get("powder_shortfall"):
        if snap.get("reload_blocks_accumulation") and not last_snapshot.get(
            "reload_blocks_accumulation"
        ):
            if "reload_blocks_accumulation" not in reasons:
                reasons.append("powder_shortfall:reload_blocks")
        if snap.get("reload_phase") in ("armed", "executing") and last_snapshot.get(
            "reload_phase"
        ) not in ("armed", "executing"):
            if "reload_armed" not in reasons:
                reasons.append(f"powder_shortfall:reload_{snap.get('reload_phase')}")

    return bool(reasons), reasons


def evaluate_emergency_rules(
    hud_state: Dict[str, Any],
    *,
    emergency_rules: Dict[str, Any],
    runtime: Any,
    trading_enabled: bool,
) -> Optional[Dict[str, Any]]:
    """Force pause trading when emergency thresholds are breached."""
    if not emergency_rules.get("enabled", True):
        return None
    risk = hud_state.get("risk") or {}
    drawdown = float(risk.get("drawdown_pct") or 0.0)
    session_pnl = float(risk.get("session_pnl_xrp") or 0.0)
    dd_limit = float(emergency_rules.get("drawdown_pause_pct") or 0.0)
    loss_limit = emergency_rules.get("session_loss_pause_xrp")

    action: Optional[Dict[str, Any]] = None
    if trading_enabled and dd_limit > 0 and drawdown >= dd_limit:
        action = {
            "type": "emergency_pause",
            "reason": f"drawdown {drawdown:.2f}% >= limit {dd_limit:.2f}%",
            "changes": {"trading_enabled": False},
        }
    elif (
        trading_enabled
        and loss_limit is not None
        and float(loss_limit) > 0
        and session_pnl <= -float(loss_limit)
    ):
        action = {
            "type": "emergency_pause",
            "reason": f"session P&L {session_pnl:.2f} XRP <= -{float(loss_limit):.2f}",
            "changes": {"trading_enabled": False},
        }

    if action is None:
        return None

    base = BotConfig.load()
    merged, errors = runtime.patch_overrides(action["changes"], base=base)
    action["applied"] = not errors
    action["errors"] = errors
    action["operator_overrides"] = merged
    return action


def apply_guardrailed_changes(
    safe_changes: List[Dict[str, Any]],
    *,
    runtime: Any,
    base: BotConfig,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """Apply filtered safe changes to operator overrides."""
    if not safe_changes:
        return [], [], runtime.load_overrides()
    sanitized = {c["key"]: c["value"] for c in safe_changes}
    merged, errors = runtime.patch_overrides(sanitized, base=base)
    if errors:
        return [], errors, merged
    applied = [
        {
            "key": k,
            "value": v,
            "reason": next((c.get("reason") for c in safe_changes if c.get("key") == k), ""),
            "description": next((c.get("description") for c in safe_changes if c.get("key") == k), ""),
        }
        for k, v in sanitized.items()
    ]
    return applied, [], merged


def pause_full_skynet_mode(
    path: Path = _DEFAULT_AGENT_PATH,
    audit_path: Path = _AUDIT_PATH,
) -> Dict[str, Any]:
    """Instantly disable full autonomy; agent suggest mode may stay on."""
    with _AGENT_LOCK:
        agent = load_agent_config(path)
        agent["full_mode_enabled"] = False
        save_agent_config(agent, path)
    append_audit_entry({"event": "full_mode_paused", "by": "operator"}, path=audit_path)
    return agent


def _schedule_next_run(agent: Dict[str, Any], engine_cycle: int) -> None:
    lo = int(agent.get("interval_cycles_min", 3) or 3)
    hi = int(agent.get("interval_cycles_max", 5) or 5)
    if lo > hi:
        lo, hi = hi, lo
    gap = random.randint(lo, hi)
    agent["last_run_engine_cycle"] = engine_cycle
    agent["next_run_engine_cycle"] = engine_cycle + gap


def should_run_agent(
    agent: Dict[str, Any],
    engine_cycle: int,
    hud_state: Optional[Dict[str, Any]] = None,
    *,
    force: bool = False,
) -> bool:
    if not agent.get("agent_enabled") and not force:
        return False
    if agent.get("running"):
        return False
    allowed, _ = budget_allows_run(agent, force=force)
    if not allowed:
        return False

    next_at = int(agent.get("next_run_engine_cycle") or 0)
    scheduled = engine_cycle >= next_at if next_at > 0 else engine_cycle > 0
    if scheduled:
        return True
    if force:
        return True
    if hud_state:
        policy = agent.get("event_triggers") or _DEFAULT_EVENT_TRIGGERS
        triggered, _ = detect_significant_events(
            hud_state, agent.get("last_event_snapshot"), event_policy=policy
        )
        if not triggered:
            return False
        # Cooldown so a flurry of events does not burn the daily budget.
        gap = int((policy or {}).get("min_cycles_between_event_runs") or 0)
        last_ev = int(agent.get("last_event_run_engine_cycle") or 0)
        if gap > 0 and last_ev > 0 and (engine_cycle - last_ev) < gap:
            return False
        return True
    return False


def run_skynet_agent(
    *,
    force: bool = False,
    agent_path: Path = _DEFAULT_AGENT_PATH,
    runtime_path: Path = _RUNTIME_PATH,
) -> Dict[str, Any]:
    """Run bounded agent cycle if due (or force=True). Returns status dict."""
    with _AGENT_LOCK:
        agent = load_agent_config(agent_path)
        if not agent.get("agent_enabled") and not force:
            return {"ok": False, "skipped": True, "message": "Agent Smith mode disabled"}

        cfg = BotConfig.load()
        if not getattr(cfg, "alpha_skynet_enabled", True):
            return {"ok": False, "message": "SKYNET disabled in config"}
        api_key = resolve_grok_key(getattr(cfg, "alpha_grok_api_key", "") or "")
        if not api_key:
            return {"ok": False, "message": "SKYNET API key not configured"}

        hud_state = _load_hud_state(runtime_path)
        engine_cycle = int(hud_state.get("engine_cycle") or 0)
        refresh_daily_budget(agent)
        allowed, budget_note = budget_allows_run(agent, force=force)
        if not allowed:
            return {
                "ok": True,
                "skipped": True,
                "budget_exhausted": True,
                "message": "Daily Agent Smith call budget exhausted — wait for UTC midnight or raise daily_call_budget",
                "engine_cycle": engine_cycle,
                "daily_calls_used": agent.get("daily_calls_used"),
                "daily_call_budget": agent.get("daily_call_budget"),
                "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
            }
        if not force and not should_run_agent(agent, engine_cycle, hud_state):
            return {
                "ok": True,
                "skipped": True,
                "engine_cycle": engine_cycle,
                "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
                "budget_remaining": budget_remaining(agent),
            }

        if agent.get("running"):
            return {"ok": False, "message": "Agent Smith already running"}

        agent["running"] = True
        save_agent_config(agent)

    event_reasons: List[str] = []
    emergency_action: Optional[Dict[str, Any]] = None
    full_mode = False
    event_driven = False

    try:
        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            full_mode = bool(agent.get("full_mode_enabled"))
            emergency_rules = agent.get("emergency_rules") or _DEFAULT_EMERGENCY_RULES
            event_policy = agent.get("event_triggers") or _DEFAULT_EVENT_TRIGGERS

        base = BotConfig.load()
        from alpha.operator.runtime import OperatorRuntimeStore

        runtime = OperatorRuntimeStore()
        overrides = runtime.load_overrides()
        effective = apply_overrides(base, overrides)
        effective_snap = effective_config_snapshot(effective, overrides)
        trading_enabled = bool(
            effective_snap.get("trading_enabled", getattr(effective, "trading_enabled", True))
        )

        emergency_action = evaluate_emergency_rules(
            hud_state,
            emergency_rules=emergency_rules,
            runtime=runtime,
            trading_enabled=trading_enabled,
        )
        if emergency_action and emergency_action.get("applied"):
            append_audit_entry(
                {
                    "event": "emergency_pause",
                    "engine_cycle": engine_cycle,
                    "reason": emergency_action.get("reason"),
                    "applied_changes": emergency_action.get("changes"),
                    "mode": "full" if full_mode else "agent",
                }
            )
            overrides = runtime.load_overrides()
            effective = apply_overrides(base, overrides)
            effective_snap = effective_config_snapshot(effective, overrides)

        next_at = int(agent.get("next_run_engine_cycle") or 0)
        scheduled = engine_cycle >= next_at if next_at > 0 else True
        triggered, event_reasons = detect_significant_events(
            hud_state, agent.get("last_event_snapshot"), event_policy=event_policy
        )
        event_driven = bool(triggered) and not scheduled and not force

        context = build_skynet_context(
            hud_state, operator_config=effective_snap, effective_config=effective
        )

        guardrails = load_agent_config(agent_path).get("guardrails") or _DEFAULT_GUARDRAILS
        max_changes = int(guardrails.get("max_changes_per_cycle", 3) or 3)
        allowed = ", ".join(OPERATOR_TUNABLE_KEYS)
        prompt_tpl = _FULL_MODE_SYSTEM_PROMPT if full_mode else _AGENT_SYSTEM_PROMPT
        user_tpl = _FULL_MODE_USER_PROMPT if full_mode else _AGENT_USER_PROMPT
        system = prompt_tpl.format(
            allowed_keys=allowed,
            guardrail_lines=_guardrail_prompt_lines(guardrails),
            max_changes=max_changes,
        )
        user_prompt = user_tpl.format(context=context)
        model = (getattr(cfg, "alpha_skynet_grok_model", None) or "grok-3").strip() or "grok-3"
        # Prefer agent max_tokens (token saver); fall back to config agent then manual caps.
        agent_cfg_tokens = int(agent.get("max_tokens") or 0)
        if agent_cfg_tokens <= 0:
            agent_cfg_tokens = int(getattr(cfg, "alpha_skynet_agent_max_tokens", 1536) or 1536)
        max_tokens = max(256, min(8192, agent_cfg_tokens))
        operator_phase = effective_snap.get("alpha_operator_phase")
        raw, parsed = call_skynet_advisor(
            user_prompt="",
            context=context,
            api_key=api_key,
            model=model,
            system_prompt=system,
            user_message=user_prompt,
            max_tokens=max_tokens,
            operator_phase=operator_phase,
        )

        safe, rejected, errors = filter_guardrailed_suggestions(
            parsed.get("suggested_changes") or [],
            guardrails=guardrails,
            base=base,
            current_effective=effective_snap,
        )

        applied_changes: List[Dict[str, Any]] = []
        apply_errors: List[str] = []
        auto_applied = False
        if full_mode and safe and not emergency_action:
            applied_changes, apply_errors, _ = apply_guardrailed_changes(
                safe, runtime=runtime, base=base
            )
            auto_applied = bool(applied_changes) and not apply_errors

        source = "full_mode" if full_mode else "agent"
        proposal = {
            "ts": _utc_now(),
            "engine_cycle": engine_cycle,
            "mode": source,
            "event_driven": event_driven,
            "event_triggers": event_reasons,
            "summary": parsed.get("summary"),
            "reasoning": parsed.get("reasoning"),
            "warnings": parsed.get("warnings") or [],
            "safe_changes": safe,
            "rejected_changes": rejected,
            "apply_errors": errors + apply_errors,
            "auto_applied": auto_applied,
            "applied_changes": applied_changes,
            "emergency_action": emergency_action,
            "max_tokens": max_tokens,
            "display": format_agent_proposal_display(
                parsed,
                safe_changes=safe,
                rejected=rejected,
                source=source,
            ),
            "raw_response": raw,
            "model": model,
        }
        if auto_applied:
            proposal["display"] += "\n\n✓ Auto-applied " + str(len(applied_changes)) + " change(s) (Full SKYNET mode)."

        append_audit_entry(
            {
                "event": "agent_run",
                "engine_cycle": engine_cycle,
                "mode": source,
                "event_driven": event_driven,
                "event_triggers": event_reasons,
                "summary": proposal.get("summary"),
                "reasoning": proposal.get("reasoning"),
                "safe_changes": safe,
                "rejected_changes": rejected,
                "applied_changes": applied_changes,
                "auto_applied": auto_applied,
                "emergency_action": emergency_action,
                "warnings": proposal.get("warnings"),
                "max_tokens": max_tokens,
            }
        )

        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            agent["running"] = False
            agent["last_run_utc"] = proposal["ts"]
            agent["last_event_snapshot"] = _event_snapshot(hud_state)
            record_budget_call(agent)
            if event_driven or event_reasons:
                agent["last_event_run_engine_cycle"] = engine_cycle
            _schedule_next_run(agent, engine_cycle)
            agent["latest_proposal"] = proposal
            save_agent_config(agent)

        logger.info(
            "skynet_agent_run | mode=%s | cycle=%s | safe=%d | rejected=%d | auto=%s | "
            "event=%s | budget_used=%s/%s",
            source,
            engine_cycle,
            len(safe),
            len(rejected),
            auto_applied,
            event_driven,
            agent.get("daily_calls_used"),
            agent.get("daily_call_budget"),
        )
        return {
            "ok": True,
            "ran": True,
            "full_mode_enabled": full_mode,
            "engine_cycle": engine_cycle,
            "proposal": proposal,
            "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
            "daily_calls_used": agent.get("daily_calls_used"),
            "daily_call_budget": agent.get("daily_call_budget"),
            "budget_remaining": budget_remaining(agent),
            "event_driven": event_driven,
        }
    except Exception as exc:
        logger.warning("skynet_agent_failed | %s", exc)
        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            agent["running"] = False
            save_agent_config(agent)
        return {"ok": False, "message": str(exc)[:800]}
    finally:
        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            if agent.get("running"):
                agent["running"] = False
                save_agent_config(agent)


def maybe_run_agent_tick() -> None:
    """Background hook: run agent when engine cycle threshold is met."""
    try:
        run_skynet_agent(force=False)
    except Exception as exc:
        logger.warning("skynet_agent_tick | %s", exc)


def agent_status_payload() -> Dict[str, Any]:
    agent = load_agent_config()
    refresh_daily_budget(agent)
    hud = _load_hud_state()
    engine_cycle = int(hud.get("engine_cycle") or 0)
    proposal = agent.get("latest_proposal")
    policy = agent.get("event_triggers") or _DEFAULT_EVENT_TRIGGERS
    triggered, event_reasons = detect_significant_events(
        hud, agent.get("last_event_snapshot"), event_policy=policy
    )
    remaining = budget_remaining(agent)
    return {
        "agent_enabled": bool(agent.get("agent_enabled")),
        "full_mode_enabled": bool(agent.get("full_mode_enabled")),
        "interval_cycles_min": agent.get("interval_cycles_min"),
        "interval_cycles_max": agent.get("interval_cycles_max"),
        "daily_call_budget": agent.get("daily_call_budget"),
        "daily_calls_used": agent.get("daily_calls_used"),
        "budget_day_utc": agent.get("budget_day_utc"),
        "budget_remaining": remaining,
        "max_tokens": agent.get("max_tokens"),
        "event_triggers": policy,
        "guardrails": agent.get("guardrails"),
        "emergency_rules": agent.get("emergency_rules"),
        "engine_cycle": engine_cycle,
        "last_run_engine_cycle": agent.get("last_run_engine_cycle"),
        "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
        "last_event_run_engine_cycle": agent.get("last_event_run_engine_cycle"),
        "last_run_utc": agent.get("last_run_utc"),
        "running": bool(agent.get("running")),
        "due": should_run_agent(agent, engine_cycle, hud),
        "event_triggered": triggered,
        "event_reasons": event_reasons,
        "latest_proposal": proposal,
        "recent_audit": load_audit_entries(limit=15),
    }
