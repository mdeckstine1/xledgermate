"""Track operator actions for auto profile switching idle timer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ACTIVITY_PATH = Path("logs/operator_activity.json")

__all__ = [
    "touch_operator_activity",
    "touch_save_config_activity",
    "minutes_since_last_operator_action",
    "minutes_since_save_config",
]


def _load_activity() -> Dict[str, Any]:
    if not ACTIVITY_PATH.exists():
        return {}
    try:
        data = json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_activity(data: Dict[str, Any]) -> None:
    ACTIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVITY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def touch_operator_activity(action: str = "save_config") -> None:
    """Record last GUI action (any). Does not reset auto-switch idle unless save_config."""
    now = datetime.now(tz=timezone.utc).isoformat()
    data = _load_activity()
    data["last_action"] = action
    data["last_action_utc"] = now
    if action == "save_config":
        data["last_save_config_utc"] = now
    _save_activity(data)


def touch_save_config_activity() -> None:
    touch_operator_activity("save_config")


def minutes_since_last_operator_action(default_minutes: float = 9999.0) -> float:
    data = _load_activity()
    ts = data.get("last_action_utc")
    return _minutes_since(ts, default_minutes)


def minutes_since_save_config(default_minutes: float = 9999.0) -> float:
    """Idle timer for auto profile switching — only Save Config resets this."""
    data = _load_activity()
    ts = data.get("last_save_config_utc") or data.get("last_action_utc")
    if data.get("last_action") == "save_config":
        ts = data.get("last_save_config_utc") or ts
    return _minutes_since(ts, default_minutes)


def _minutes_since(ts: Any, default_minutes: float) -> float:
    if not ts:
        return default_minutes
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        delta = datetime.now(tz=timezone.utc) - last.astimezone(timezone.utc)
        return max(0.0, delta.total_seconds() / 60.0)
    except (ValueError, TypeError):
        return default_minutes
