"""Structured activity log for operator GUI and audits."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("logs/alpha_activity.jsonl")


class ActivityLog:
    """Append-only JSONL — decisions, fills, errors (no secrets)."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, **fields: Any) -> None:
        row: Dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
        except OSError as exc:
            logger.warning("activity_log_write_failed | %s", exc)

    def tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.path.exists() or limit <= 0:
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            except json.JSONDecodeError:
                continue
        return out
