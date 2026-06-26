"""Treasury integration placeholder — sideline capital routing (not implemented)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_PLACEHOLDER_PATH = Path("logs/alpha_treasury.json")


def treasury_placeholder_status(*, logs_dir: str | Path = "logs") -> Dict[str, Any]:
    """Return stub treasury status for HUD PRO tab."""
    path = Path(logs_dir) / "alpha_treasury.json"
    stored: Dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                stored = raw
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "status": "placeholder",
        "implemented": False,
        "message": (
            "Treasury automation (Tangem / cold-wallet tranche deploy) is not wired yet. "
            "Use Config → RLUSD issuer + Xaman manual funding until Phase 2."
        ),
        "planned_features": [
            "sideline_balance_xrp_equiv",
            "tranche_deploy_rules",
            "auto_top_up_when_drawdown",
            "cold_wallet_address_book",
        ],
        "last_updated_utc": stored.get("last_updated_utc")
        or datetime.now(tz=timezone.utc).isoformat(),
        "notes": stored.get("notes") or [],
    }
