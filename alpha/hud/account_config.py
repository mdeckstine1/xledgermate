"""Alpha HUD account config — read/write bot credentials and operator IDs."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config.settings import BotConfig, patch_config_file

_SECRET_PLACEHOLDER = "••••••••"

# Writable via HUD Config tab (credentials → sidecar on save).
ACCOUNT_CONFIG_KEYS: Tuple[str, ...] = (
    "bot_account_address",
    "bot_secret_key",
    "testnet",
    "rlusd_issuer",
    "xrp_reserve",
    "send_destination_default",
    "telegram_enabled",
    "telegram_token",
    "telegram_chat_id",
    "telegram_hud_url",
    "hud_auth_username",
    "hud_auth_password",
    "private_node_url",
)

_SECRET_FIELDS = frozenset({"bot_secret_key", "telegram_token", "hud_auth_password"})


def _mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "••••"
    return f"{raw[:2]}••••{raw[-2:]}"


def account_config_snapshot(config: BotConfig | None = None) -> Dict[str, Any]:
    cfg = config or BotConfig.load()
    secret = (cfg.bot_secret_key or "").strip()
    tg_token = (cfg.telegram_token or "").strip()
    hud_pw = (cfg.hud_auth_password or "").strip()
    return {
        "bot_account_address": (cfg.bot_account_address or "").strip(),
        "has_bot_secret": bool(secret),
        "bot_secret_masked": _mask_secret(secret),
        "testnet": bool(cfg.testnet),
        "network": cfg.network_name(),
        "rpc_url": cfg.resolved_rpc_url(),
        "rlusd_issuer": cfg.resolved_rlusd_issuer(),
        "rlusd_issuer_override": (cfg.rlusd_issuer or "").strip(),
        "xrp_reserve": float(cfg.xrp_reserve),
        "send_destination_default": (cfg.send_destination_default or "").strip(),
        "telegram_enabled": bool(cfg.telegram_enabled),
        "has_telegram_token": bool(tg_token),
        "telegram_token_masked": _mask_secret(tg_token),
        "telegram_chat_id": (cfg.telegram_chat_id or "").strip(),
        "telegram_hud_url": (cfg.telegram_hud_url or "").strip(),
        "hud_auth_username": (cfg.hud_auth_username or "").strip(),
        "has_hud_auth_password": bool(hud_pw),
        "private_node_url": (cfg.private_node_url or "").strip(),
        "credentials_sidecar": "config/credentials.local.yaml",
    }


def _is_placeholder_secret(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text == _SECRET_PLACEHOLDER or "••••" in text


def apply_account_config_updates(updates: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Persist account config; secrets blank/placeholder leave existing values."""
    errors: List[str] = []
    allowed = {f.name for f in fields(BotConfig)}
    cfg = BotConfig.load()

    for key, raw in updates.items():
        if key not in ACCOUNT_CONFIG_KEYS or key not in allowed:
            errors.append(f"unknown or disallowed key: {key}")
            continue
        if key in _SECRET_FIELDS and _is_placeholder_secret(raw):
            continue
        if key == "bot_account_address":
            addr = str(raw or "").strip()
            if addr and not addr.startswith("r"):
                errors.append("bot_account_address must start with r")
                continue
            setattr(cfg, key, addr)
        elif key in ("testnet", "telegram_enabled"):
            setattr(cfg, key, bool(raw))
        elif key == "xrp_reserve":
            try:
                val = float(raw)
            except (TypeError, ValueError):
                errors.append("xrp_reserve must be a number")
                continue
            if val < 0:
                errors.append("xrp_reserve must be >= 0")
                continue
            setattr(cfg, key, val)
        elif key in _SECRET_FIELDS:
            setattr(cfg, key, str(raw).strip())
        else:
            setattr(cfg, key, str(raw).strip() if raw is not None else "")

    if errors:
        return account_config_snapshot(cfg), errors

    cfg.save()
    non_secret = (
        "bot_account_address",
        "testnet",
        "rlusd_issuer",
        "xrp_reserve",
        "send_destination_default",
        "telegram_enabled",
        "telegram_chat_id",
        "telegram_hud_url",
        "hud_auth_username",
        "private_node_url",
    )
    patch_config_file({k: getattr(cfg, k) for k in non_secret if k in allowed})
    return account_config_snapshot(cfg), []


def read_recent_transfers(*, limit: int = 25) -> List[Dict[str, str]]:
    path = Path("logs/transfers.csv")
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    if len(lines) <= 1:
        return []
    rows: List[Dict[str, str]] = []
    header = [h.strip() for h in lines[0].split(",")]
    for line in lines[1:][-limit:]:
        parts = line.split(",")
        if len(parts) < len(header):
            continue
        rows.append({header[i]: parts[i] for i in range(len(header))})
    return list(reversed(rows))


def is_alpha_engine_running() -> bool:
    unit = Path("/etc/systemd/system/xledgermate-alpha.service")
    if not unit.is_file():
        return False
    import subprocess

    proc = subprocess.run(
        ["systemctl", "is-active", "xledgermate-alpha"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip() == "active"
