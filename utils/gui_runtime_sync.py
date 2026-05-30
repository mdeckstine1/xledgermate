"""GUI-only patches to logs/runtime_state.json (kept out of core.runtime_state for Streamlit reload)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def patch_runtime_state_file(
    updates: Dict[str, Any],
    *,
    path: str | Path = "logs/runtime_state.json",
) -> bool:
    """Merge keys into runtime_state.json so the GUI reflects config changes while stopped."""
    file_path = Path(path)
    if not file_path.exists():
        return False
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data.update(updates)
        data["updated_utc"] = datetime.now(tz=timezone.utc).isoformat()
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return False
