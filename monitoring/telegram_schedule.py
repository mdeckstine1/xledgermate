"""Telegram hourly report scheduling helpers (quiet hours + systemd timer)."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional, Tuple


def is_quiet_hour(
    hour: int,
    *,
    start_hour: int,
    end_hour: int,
) -> bool:
    """Return True if `hour` (0–23 UTC) falls in [start, end) with midnight wrap."""
    start_hour = int(start_hour) % 24
    end_hour = int(end_hour) % 24
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def hourly_report_allowed_now(
    *,
    quiet_hours_enabled: bool,
    quiet_start_hour: int,
    quiet_end_hour: int,
    now: Optional[datetime] = None,
) -> bool:
    if not quiet_hours_enabled:
        return True
    dt = now or datetime.now(tz=timezone.utc)
    return not is_quiet_hour(dt.hour, start_hour=quiet_start_hour, end_hour=quiet_end_hour)


def quiet_hours_label(start_hour: int, end_hour: int) -> str:
    return f"{int(start_hour) % 24:02d}:00–{int(end_hour) % 24:02d}:00 UTC"


def ensure_hourly_report_timer() -> Tuple[bool, str]:
    """Enable systemd hourly timer if present (VPS). No-op elsewhere."""
    if shutil.which("systemctl") is None:
        return False, "systemctl not available"
    unit = "xledgermate-hourly-report.timer"
    try:
        subprocess.run(
            ["systemctl", "enable", "--now", unit],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, f"{unit} enabled"
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, err or "systemctl enable failed"
