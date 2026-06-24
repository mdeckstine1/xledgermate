#!/usr/bin/env python3
"""One-shot: enable bracket trailing via operator overrides (HUD-equivalent)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import BotConfig
from alpha.operator.runtime import OperatorRuntimeStore


def main() -> None:
    store = OperatorRuntimeStore()
    merged, errors = store.patch_overrides(
        {"bracket_trailing_enabled": True, "trailing_step_pct": 1.5},
        base=BotConfig.load(),
    )
    if errors:
        raise SystemExit(f"errors")
    print(
        "bracket_trailing_enabled=",
        merged.get("bracket_trailing_enabled"),
        "trailing_step_pct=",
        merged.get("trailing_step_pct"),
    )


if __name__ == "__main__":
    main()
