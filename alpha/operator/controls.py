"""Operator pause/resume controls (file-backed, survives restarts)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("logs/alpha_controls.json")


@dataclass
class OperatorControls:
    trading_paused: bool = False
    pause_reason: str = ""
    updated_utc: str = ""


class OperatorControlStore:
    """GUI/CLI can pause trading without editing config.yaml."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> OperatorControls:
        if not self.path.exists():
            return OperatorControls()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return OperatorControls(
                trading_paused=bool(data.get("trading_paused", False)),
                pause_reason=str(data.get("pause_reason", "")),
                updated_utc=str(data.get("updated_utc", "")),
            )
        except (json.JSONDecodeError, OSError):
            return OperatorControls()

    def save(self, controls: OperatorControls) -> None:
        controls.updated_utc = datetime.now(tz=timezone.utc).isoformat()
        payload = {
            "trading_paused": controls.trading_paused,
            "pause_reason": controls.pause_reason,
            "updated_utc": controls.updated_utc,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def pause(self, reason: str = "Operator pause") -> OperatorControls:
        controls = OperatorControls(trading_paused=True, pause_reason=reason)
        self.save(controls)
        logger.info("alpha_trading_paused | reason=%s", reason)
        return controls

    def resume(self) -> OperatorControls:
        controls = OperatorControls(trading_paused=False, pause_reason="")
        self.save(controls)
        logger.info("alpha_trading_resumed")
        return controls

    def is_paused(self) -> bool:
        return self.load().trading_paused
