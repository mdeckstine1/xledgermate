"""Operator-requested profile changes (picked up by the engine on the next cycle)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROFILE_REQUEST_PATH = Path("logs/profile_request.json")


def write_profile_request(profile: str) -> None:
    name = (profile or "").strip().lower()
    if not name:
        return
    PROFILE_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": name,
        "requested_utc": datetime.now(tz=timezone.utc).isoformat(),
    }
    PROFILE_REQUEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def consume_profile_request(*, known_profiles: set[str]) -> Optional[str]:
    """Return profile name if a pending request exists and is valid; clears the file."""
    if not PROFILE_REQUEST_PATH.exists():
        return None
    try:
        data = json.loads(PROFILE_REQUEST_PATH.read_text(encoding="utf-8"))
        name = str(data.get("profile", "")).strip().lower()
    except (json.JSONDecodeError, OSError, TypeError):
        PROFILE_REQUEST_PATH.unlink(missing_ok=True)
        return None
    PROFILE_REQUEST_PATH.unlink(missing_ok=True)
    if name in known_profiles:
        return name
    return None
