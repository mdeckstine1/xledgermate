#!/usr/bin/env python3
"""One-shot: enable bracket trailing via operator overrides (HUD-equivalent)."""
from __future__ import annotations

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
