"""Persistent kill switch (survives engine restarts)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

KILL_SWITCH_PATH = Path("logs/kill_switch.json")


@dataclass
class KillSwitchState:
    active: bool = False
    reason: str = ""
    activated_utc: Optional[str] = None


class KillSwitch:
    def __init__(self, path: Path = KILL_SWITCH_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> KillSwitchState:
        if not self.path.exists():
            return KillSwitchState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return KillSwitchState(
                active=bool(data.get("active", False)),
                reason=str(data.get("reason", "")),
                activated_utc=data.get("activated_utc"),
            )
        except (json.JSONDecodeError, OSError):
            return KillSwitchState()

    def _save(self) -> None:
        payload = {
            "active": self._state.active,
            "reason": self._state.reason,
            "activated_utc": self._state.activated_utc,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def activate(self, reason: str = "Drawdown limit exceeded") -> None:
        self._state = KillSwitchState(
            active=True,
            reason=reason,
            activated_utc=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._save()
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

    def clear(self, reason: str = "Operator reset") -> None:
        self._state = KillSwitchState(active=False, reason=reason, activated_utc=None)
        self._save()
        logger.info("Kill switch cleared: %s", reason)

    def is_active(self) -> bool:
        return self._state.active

    @property
    def reason(self) -> str:
        return self._state.reason
