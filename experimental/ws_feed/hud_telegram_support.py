"""HUD ↔ config.yaml for Telegram reporting settings (non-secret fields)."""

from __future__ import annotations

from typing import Any, Dict

from config.settings import BotConfig, patch_config_file
from monitoring.telegram_schedule import (
    ensure_hourly_report_timer,
    hourly_report_allowed_now,
    quiet_hours_label,
)


def telegram_config_snapshot(config: BotConfig | None = None) -> Dict[str, Any]:
    cfg = config or BotConfig.load()
    quiet_start = int(getattr(cfg, "telegram_quiet_start_hour", 22))
    quiet_end = int(getattr(cfg, "telegram_quiet_end_hour", 7))
    quiet_enabled = bool(getattr(cfg, "telegram_quiet_hours_enabled", False))
    allowed = hourly_report_allowed_now(
        quiet_hours_enabled=quiet_enabled,
        quiet_start_hour=quiet_start,
        quiet_end_hour=quiet_end,
    )
    return {
        "telegram_enabled": bool(cfg.telegram_enabled),
        "telegram_hourly_report_enabled": bool(
            getattr(cfg, "telegram_hourly_report_enabled", True)
        ),
        "telegram_kill_alerts_enabled": bool(
            getattr(cfg, "telegram_kill_alerts_enabled", True)
        ),
        "telegram_hud_url": str(getattr(cfg, "telegram_hud_url", "") or ""),
        "telegram_quiet_hours_enabled": quiet_enabled,
        "telegram_quiet_start_hour": quiet_start,
        "telegram_quiet_end_hour": quiet_end,
        "telegram_quiet_label": quiet_hours_label(quiet_start, quiet_end),
        "hourly_report_allowed_now": allowed,
        "telegram_configured": bool(
            cfg.telegram_enabled and cfg.telegram_token and cfg.telegram_chat_id
        ),
    }


def apply_telegram_config_from_hud(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Patch config.yaml telegram keys; ensure hourly timer when reports enabled."""
    updates: Dict[str, Any] = {}

    if "telegram_enabled" in payload:
        updates["telegram_enabled"] = bool(payload["telegram_enabled"])
    if "hourly_enabled" in payload:
        updates["telegram_hourly_report_enabled"] = bool(payload["hourly_enabled"])
    if "kill_alerts_enabled" in payload:
        updates["telegram_kill_alerts_enabled"] = bool(payload["kill_alerts_enabled"])
    if "hud_url" in payload:
        updates["telegram_hud_url"] = str(payload.get("hud_url") or "").strip()
    if "quiet_hours_enabled" in payload:
        updates["telegram_quiet_hours_enabled"] = bool(payload["quiet_hours_enabled"])
    if "quiet_start_hour" in payload:
        updates["telegram_quiet_start_hour"] = int(payload["quiet_start_hour"]) % 24
    if "quiet_end_hour" in payload:
        updates["telegram_quiet_end_hour"] = int(payload["quiet_end_hour"]) % 24

    if updates:
        patch_config_file(updates)

    timer_ok = False
    timer_msg = ""
    cfg = BotConfig.load()
    if cfg.telegram_enabled and getattr(cfg, "telegram_hourly_report_enabled", True):
        timer_ok, timer_msg = ensure_hourly_report_timer()

    snap = telegram_config_snapshot(cfg)
    snap["timer_ok"] = timer_ok
    snap["timer_message"] = timer_msg
    return snap
