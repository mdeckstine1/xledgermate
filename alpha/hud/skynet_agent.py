"""Alpha SKYNET Phase 2 — bounded Grok agent with guardrailed auto-suggest."""

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
_AGENT_LOCK = threading.Lock()

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
    "max_changes_per_cycle": 2,
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
"""

_AGENT_USER_PROMPT = """Autonomous agent review (Phase 2). Analyze the full runtime context below.

Decide whether bounded knob adjustments would improve bag growth without violating guardrails.
If the bot is on HOLD, explain why and only suggest changes if they address the block constructively.

Context:
{context}
"""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def default_agent_config() -> Dict[str, Any]:
    return {
        "agent_enabled": False,
        "interval_cycles_min": 3,
        "interval_cycles_max": 5,
        "guardrails": deepcopy(_DEFAULT_GUARDRAILS),
        "last_run_engine_cycle": 0,
        "next_run_engine_cycle": 0,
        "last_run_utc": None,
        "running": False,
        "latest_proposal": None,
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
    for key in ("agent_enabled", "interval_cycles_min", "interval_cycles_max"):
        if key in data:
            cfg[key] = data[key]
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
    ):
        if key in data:
            cfg[key] = data[key]
    return cfg


def save_agent_config(config: Dict[str, Any], path: Path = _DEFAULT_AGENT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


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


def _schedule_next_run(agent: Dict[str, Any], engine_cycle: int) -> None:
    lo = int(agent.get("interval_cycles_min", 3) or 3)
    hi = int(agent.get("interval_cycles_max", 5) or 5)
    if lo > hi:
        lo, hi = hi, lo
    gap = random.randint(lo, hi)
    agent["last_run_engine_cycle"] = engine_cycle
    agent["next_run_engine_cycle"] = engine_cycle + gap


def should_run_agent(agent: Dict[str, Any], engine_cycle: int) -> bool:
    if not agent.get("agent_enabled"):
        return False
    if agent.get("running"):
        return False
    next_at = int(agent.get("next_run_engine_cycle") or 0)
    if next_at <= 0:
        return engine_cycle > 0
    return engine_cycle >= next_at


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
        if not force and not should_run_agent(agent, engine_cycle):
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

    try:
        base = BotConfig.load()
        from alpha.operator.runtime import OperatorRuntimeStore

        runtime = OperatorRuntimeStore()
        overrides = runtime.load_overrides()
        effective = apply_overrides(base, overrides)
        effective_snap = effective_config_snapshot(effective)
        context = build_skynet_context(hud_state, operator_config=effective_snap)

        guardrails = agent.get("guardrails") or _DEFAULT_GUARDRAILS
        max_changes = int(guardrails.get("max_changes_per_cycle", 2) or 2)
        allowed = ", ".join(OPERATOR_TUNABLE_KEYS)
        system = _AGENT_SYSTEM_PROMPT.format(
            allowed_keys=allowed,
            guardrail_lines=_guardrail_prompt_lines(guardrails),
            max_changes=max_changes,
        )
        user_prompt = _AGENT_USER_PROMPT.format(context=context)
        model = (getattr(cfg, "alpha_skynet_grok_model", None) or "grok-3").strip() or "grok-3"
        raw, parsed = call_grok_advisor(
            user_prompt="",
            context=context,
            api_key=api_key,
            model=model,
            system_prompt=system,
            user_message=user_prompt,
        )

        safe, rejected, errors = filter_guardrailed_suggestions(
            parsed.get("suggested_changes") or [],
            guardrails=guardrails,
            base=base,
            current_effective=effective_snap,
        )
        proposal = {
            "ts": _utc_now(),
            "engine_cycle": engine_cycle,
            "summary": parsed.get("summary"),
            "reasoning": parsed.get("reasoning"),
            "warnings": parsed.get("warnings") or [],
            "safe_changes": safe,
            "rejected_changes": rejected,
            "apply_errors": errors,
            "display": format_agent_proposal_display(
                parsed,
                safe_changes=safe,
                rejected=rejected,
                source="agent",
            ),
            "raw_response": raw,
            "model": model,
        }

        with _AGENT_LOCK:
            agent = load_agent_config(agent_path)
            agent["running"] = False
            agent["last_run_utc"] = proposal["ts"]
            _schedule_next_run(agent, engine_cycle)
            agent["latest_proposal"] = proposal
            save_agent_config(agent)

        logger.info(
            "skynet_agent_run | cycle=%s | safe=%d | rejected=%d",
            engine_cycle,
            len(safe),
            len(rejected),
        )
        return {
            "ok": True,
            "ran": True,
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
    return {
        "agent_enabled": bool(agent.get("agent_enabled")),
        "interval_cycles_min": agent.get("interval_cycles_min"),
        "interval_cycles_max": agent.get("interval_cycles_max"),
        "guardrails": agent.get("guardrails"),
        "engine_cycle": engine_cycle,
        "last_run_engine_cycle": agent.get("last_run_engine_cycle"),
        "next_run_engine_cycle": agent.get("next_run_engine_cycle"),
        "last_run_utc": agent.get("last_run_utc"),
        "running": bool(agent.get("running")),
        "due": should_run_agent(agent, engine_cycle),
        "latest_proposal": proposal,
    }
