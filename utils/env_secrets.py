"""Load local .env secrets (gitignored). No external dependencies."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOADED = False


def load_dotenv_local(repo_root: Optional[Path] = None) -> None:
    """Parse repo-root `.env` into os.environ (does not override existing vars)."""
    global _LOADED
    root = repo_root or _REPO_ROOT
    env_file = root / ".env"
    if not env_file.is_file():
        _LOADED = True
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    _LOADED = True


def resolve_grok_key(explicit: str = "") -> str:
    load_dotenv_local()
    return (explicit or "").strip() or os.environ.get("XLG_GROK_KEY", "").strip() or os.environ.get(
        "XAI_API_KEY", ""
    ).strip()


def resolve_intel_ai_config(
    *,
    provider: str = "stub",
    api_key: str = "",
    model: str = "grok-3",
) -> Tuple[str, str, str]:
    """
    Merge CLI args with .env / process env.

    XLG_GROK_KEY + XLG_INTEL_AI_PROVIDER=grok (default when key present) pre-fills HUD + calibration.
    """
    load_dotenv_local()
    key = resolve_grok_key(api_key)
    model = (model or "").strip() or os.environ.get("XLG_GROK_MODEL", "grok-3").strip() or "grok-3"
    prov = (provider or "").strip()
    if not prov or prov == "stub":
        prov = os.environ.get("XLG_INTEL_AI_PROVIDER", "grok" if key else "stub").strip() or "stub"
    if not key:
        prov = prov if prov != "grok" else "stub"
    return prov, key, model
