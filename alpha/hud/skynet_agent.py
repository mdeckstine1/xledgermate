"""Alpha SKYNET Phase 2/3 — bounded Grok agent with optional supervised autonomy."""

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
    call_grok_advisor,
    filter_applicable_suggestions,
    format_advisor_display,
    parse_grok_advisor_response,
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

_DEFAULT_GUARDRAILS: Dict[str, Any] = {
    "alpha_risk_per_trade_pct": {"min": 0.1, "max": 2.0},
    "inventory_target_xrp_pct": {"min": 50.0, "max": 92.0},
    "alpha_ta_weight": {"min": 0.0, "max": 1.0},
    "alpha_reentry_tp_cooldown_cycles": {"min": 0, "max": 30},
    "alpha_reentry_tp_cooldown_minutes": {"min": 0.0, "max": 180.0},
    "alpha_reentry_sl_cooldown_cycles": {"min": 0, "max": 60},
    "alpha_reentry_sl_cooldown_minutes": {"min": 0.0, "max": 480.0},
    "max_changes_per_cycle": 3,
}

_DEFAULT_EMERGENCY_RULES: Dict[str, Any] = {
    "enabled": True,
    "drawdown_pause_pct": 8.0,
    "session_loss_pause_xrp": 25.0,
}

_AGENT_SYSTEM_PROMPT = """You are SKYNET Agent for xLedgerMate Alpha — a bounded configuration advisor for an XRPL XRP/RLUSD bag-growth bot.

You analyze runtime state and may suggest operator knob changes ONLY when they improve long-term XRP bag growth while respecting risk.

Respond with a single JSON object (no markdown fences):
{{
  "reasoning": "<3-8 sentences: inventory, TA, decision/HOLD reasons, market conditions, brackets>",
  "summary": "<one-line headline>",
  "suggested_changes": [
    {{"key": "<operator_config_key>", "value": <json_value>, "reason": "<why this knob, tied to current state>"}}
  ],
  "warnings": ["<optional safety warnings>"]
}}

Hard rules:
- Only keys from this allowlist: {allowed_keys}
- NEVER suggest dry_run changes.
- NEVER exceed these guardrails (values must stay inside min/max):
{guardrail_lines}
- Suggest at most {max_changes} change(s) per response.
- inventory_target_xrp_ratio is 0.0-1.0 (not percent). Prefer inventory_target_xrp_ratio over target_xrp_pct.
- Explain each suggested knob change with reference to current effective values in context.
- If no safe improvement is warranted, return an empty suggested_changes array and explain why in reasoning.
- Small incremental adjustments only — no reckless risk increases.
- Pending buys are passive limit bids (fill when ask hits bid, not when mid crosses). Use `pending_buy_stale` in context: if `would_cancel_count` is high or `over_cap_count` > 0, consider lowering `alpha_stale_pending_buy_max_drift_pct` (align with `alpha_buy_limit_offset_pct`), reducing `alpha_max_pending_buys`, or setting `alpha_stale_pending_buy_max_age_seconds`.
"""

_AGENT_USER_PROMPT = """Autonomous agent review (Phase 2). Analyze the full runtime context below.

Decide whether bounded knob adjustments would improve bag growth without violating guardrails.
If the bot is on HOLD, explain why and only suggest changes if they address the block constructively.

Context:
{context}
"""

_FULL_MODE_SYSTEM_PROMPT = """You are SKYNET Full Mode — a disciplined, risk-aware meta-operator for xLedgerMate Alpha on XRPL XRP/RLUSD.

Your mandate: maximize long-term XRP bag growth while protecting capital. You operate under strict human guardrails. Changes you propose may be auto-applied when inside bounds.

Respond with a single JSON object (no markdown fences):
{{
  "reasoning": "<clear 4-10 sentences: inventory deviation, TA scores, decision/HOLD reasons, market conditions, liquidity, recent performance, brackets>",
  "summary": "<one-line headline for the operator>",
  "suggested_changes": [
    {{"key": "<operator_config_key>", "value": <json_value>, "reason": "<why this knob, tied to current state>"}}
  ],
  "warnings": ["<optional safety warnings>"]
}}

Trading discipline (non-negotiable):
- Prioritize capital preservation after losses or elevated drawdown — be conservative, not reactive.
- Never chase; prefer patience when TA blocks entries or inventory is already heavy XRP / light RLUSD to deploy.
- Small incremental knob moves only. Never stack aggressive risk increases in one cycle.
- If HOLD is correct, say so — empty suggested_changes is valid and often best.
- NEVER suggest dry_run changes. NEVER exceed guardrails below.
- inventory_target_xrp_ratio is 0.0-1.0 (not percent). Prefer inventory_target_xrp_ratio over target_xrp_pct.
- Explain every suggestion with reference to effective values in context.

Allowlist only: {allowed_keys}

Guardrails (min/max — stay inside):
{guardrail_lines}

Max {max_changes} change(s) per response.

Emergency context: if drawdown is elevated or session P&L is negative, bias toward defense (lower risk, widen cooldowns, reduce TA aggression) — never the opposite without strong justification.

Pending buy ladder: context includes `pending_buy_stale` with per-bid `would_cancel` / `reason`. Loose `alpha_stale_pending_buy_max_drift_pct` (e.g. 0.5% vs offset 0.15–0.35%) lets many old bids rest unfilled. Prefer aligning drift to offset and capping `alpha_max_pending_buys`. Cancels are one ledger offer per engine cycle.
"""

_FULL_MODE_USER_PROMPT = """Full SKYNET autonomy review (Phase 3). Analyze the complete runtime context.

Decide whether bounded knob adjustments would improve bag growth without violating guardrails.
If the bot is on HOLD, explain why and only suggest changes that constructively address the block.
If recent performance is weak, prioritize capital protection over aggression.

Context:
{context}
"""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def default_agent_config() -> Dict[str, Any]:
    return {
        "agent_enabled": False,
        "full_mode_enabled": False,
        "interval_cycles_min": 3,
        "interval_cycles_max": 5,
        "guardrails": deepcopy(_DEFAULT_GUARDRAILS),
        "emergency_rules": deepcopy(_DEFAULT_EMERGENCY_RULES),
        "last_run_engine_cycle": 0,
        "next_run_engine_cycle": 0,
        "last_run_utc": None,
        "running": False,
        "latest_proposal": None,
        "last_event_snapshot": None,
    }


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
    for key in ("agent_enabled", "full_mode_enabled", "interval_cycles_min", "interval_cycles_max"):
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
                current[key] = val
            except (TypeError, ValueError) as exc:
                errors.append(f"{key}: {exc}")

    if current["interval_cycles_min"] > current["interval_cycles_max"]:
        errors.append("interval_cycles_min cannot exceed interval_cycles_max")

    if "guardrails" in patch and isinstance(patch["guardrails"], dict):
        merged = deepcopy(current.get("guardrails") or _DEFAULT_GUARDRAILS)
        merged.update(patch["guardrails"])
        current["guardrails"] = _normalize_guardrails(merged)

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
    lines = []
    for key in (
        "alpha_risk_per_trade_pct",
        "inventory_target_xrp_pct",
        "alpha_ta_weight",
        *_COOLDOWN_GUARD_KEYS,
    ):
        bounds = guardrails.get(key)
        if isinstance(bounds, dict):
            lines.append(f"- {key}: min={bounds.get('min')} max={bounds.get('max')}")
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
    return {
        "engine_cycle": int(hud_state.get("engine_cycle") or 0),
        "decision_action": str(decision.get("action") or ""),
        "kill_switch_active": bool(risk.get("kill_switch_active")),
        "drawdown_pct": float(risk.get("drawdown_pct") or 0.0),
        "session_pnl_xrp": float(risk.get("session_pnl_xrp") or 0.0),
        "inventory_deviation": float(inv.get("deviation") or 0.0),
        "trading_enabled": hud_state.get("trading_enabled"),
    }


def detect_significant_events(
    hud_state: Dict[str, Any],
    last_snapshot: Optional[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Return (triggered, reasons) for event-driven agent runs."""
    if not hud_state:
        return False, []
    snap = _event_snapshot(hud_state)
    if not last_snapshot:
        return False, []

    reasons: List[str] = []
    if snap["kill_switch_active"] and not last_snapshot.get("kill_switch_active"):
        reasons.append("kill_switch_activated")
    if snap["decision_action"] and snap["decision_action"] != last_snapshot.get("decision_action"):
        reasons.append(f"decision_changed:{last_snapshot.get('decision_action')}→{snap['decision_action']}")
    dd_delta = snap["drawdown_pct"] - float(last_snapshot.get("drawdown_pct") or 0.0)
    if dd_delta >= 1.0:
        reasons.append(f"drawdown_spike:+{dd_delta:.2f}pct")
    pnl_delta = snap["session_pnl_xrp"] - float(last_snapshot.get("session_pnl_xrp") or 0.0)
    if pnl_delta <= -5.0:
        reasons.append(f"session_loss:{pnl_delta:.2f}xrp")
    dev_delta = abs(snap["inventory_deviation"] - float(last_snapshot.get("inventory_deviation") or 0.0))
    if dev_delta >= 0.12:
        reasons.append(f"inventory_shift:deviation_delta={dev_delta:.3f}")
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
) -> bool:
    if not agent.get("agent_enabled"):
        return False
    if agent.get("running"):
        return False
    next_at = int(agent.get("next_run_engine_cycle") or 0)
    scheduled = engine_cycle >= next_at if next_at > 0 else engine_cycle > 0
    if scheduled:
        return True
    if hud_state:
        triggered, _ = detect_significant_events(hud_state, agent.get("last_event_snapshot"))
        return triggered
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
            return {"ok": False, "skipped": True, "message": "Agent mode disabled"}

        cfg = BotConfig.load()
        if not getattr(cfg, "alpha_skynet_enabled", True):
            return {"ok": False, "message": "SKYNET disabled in config"}
        api_key = resolve_grok_key(getattr(cfg, "alpha_grok_api_key", "") or "")
        if not api_key:
            return {"ok": False, "message": "Grok API key not configured"}

        hud_state = _load_hud_state(runtime_path)
        engine_cycle = int(hud_state.get("engine_cycle") or 0)
        if not force and not should_run_agent(agent, engine_cycle, hud_state):
            return {
                "ok": True,
                "skipped": True,
                "engine_cycle": engine_cycle,
                "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
            }

        if agent.get("running"):
            return {"ok": False, "message": "Agent already running"}

        agent["running"] = True
        save_agent_config(agent)

    event_reasons: List[str] = []
    emergency_action: Optional[Dict[str, Any]] = None
    full_mode = False

    try:
        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            full_mode = bool(agent.get("full_mode_enabled"))
            emergency_rules = agent.get("emergency_rules") or _DEFAULT_EMERGENCY_RULES

        base = BotConfig.load()
        from alpha.operator.runtime import OperatorRuntimeStore

        runtime = OperatorRuntimeStore()
        overrides = runtime.load_overrides()
        effective = apply_overrides(base, overrides)
        effective_snap = effective_config_snapshot(effective)
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
            effective_snap = effective_config_snapshot(effective)

        triggered, event_reasons = detect_significant_events(
            hud_state, agent.get("last_event_snapshot")
        )

        context = build_skynet_context(hud_state, operator_config=effective_snap)

        guardrails = agent.get("guardrails") or _DEFAULT_GUARDRAILS
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
        max_tokens = int(getattr(cfg, "alpha_skynet_grok_max_tokens", 4096) or 4096)
        raw, parsed = call_grok_advisor(
            user_prompt="",
            context=context,
            api_key=api_key,
            model=model,
            system_prompt=system,
            user_message=user_prompt,
            max_tokens=max_tokens,
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
                "event_triggers": event_reasons,
                "summary": proposal.get("summary"),
                "reasoning": proposal.get("reasoning"),
                "safe_changes": safe,
                "rejected_changes": rejected,
                "applied_changes": applied_changes,
                "auto_applied": auto_applied,
                "emergency_action": emergency_action,
                "warnings": proposal.get("warnings"),
            }
        )

        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            agent["running"] = False
            agent["last_run_utc"] = proposal["ts"]
            agent["last_event_snapshot"] = _event_snapshot(hud_state)
            _schedule_next_run(agent, engine_cycle)
            agent["latest_proposal"] = proposal
            save_agent_config(agent)

        logger.info(
            "skynet_agent_run | mode=%s | cycle=%s | safe=%d | rejected=%d | auto=%s",
            source,
            engine_cycle,
            len(safe),
            len(rejected),
            auto_applied,
        )
        return {
            "ok": True,
            "ran": True,
            "full_mode_enabled": full_mode,
            "engine_cycle": engine_cycle,
            "proposal": proposal,
            "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
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
    hud = _load_hud_state()
    engine_cycle = int(hud.get("engine_cycle") or 0)
    proposal = agent.get("latest_proposal")
    triggered, event_reasons = detect_significant_events(hud, agent.get("last_event_snapshot"))
    return {
        "agent_enabled": bool(agent.get("agent_enabled")),
        "full_mode_enabled": bool(agent.get("full_mode_enabled")),
        "interval_cycles_min": agent.get("interval_cycles_min"),
        "interval_cycles_max": agent.get("interval_cycles_max"),
        "guardrails": agent.get("guardrails"),
        "emergency_rules": agent.get("emergency_rules"),
        "engine_cycle": engine_cycle,
        "last_run_engine_cycle": agent.get("last_run_engine_cycle"),
        "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
        "last_run_utc": agent.get("last_run_utc"),
        "running": bool(agent.get("running")),
        "due": should_run_agent(agent, engine_cycle, hud),
        "event_triggered": triggered,
        "event_reasons": event_reasons,
        "latest_proposal": proposal,
        "recent_audit": load_audit_entries(limit=15),
    }
