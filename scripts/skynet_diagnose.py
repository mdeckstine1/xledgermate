#!/usr/bin/env python3
"""Run on the VPS (or locally) to explain SKYNET Ask failures."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    from config.settings import BotConfig
    from utils.env_secrets import resolve_grok_key
    from alpha.hud.skynet import build_skynet_context, skynet_status
    from alpha.hud.skynet_scenarios import infer_scenario_hints

    print("=== SKYNET diagnose ===")
    print(f"git HEAD: {_git_head()}")
    sig = inspect.signature(infer_scenario_hints)
    has_acc = "accumulation_regime" in sig.parameters
    print(f"infer_scenario_hints.accumulation_regime param: {'OK' if has_acc else 'MISSING (Ask will crash)'}")
    if not has_acc:
        print("  FIX: git pull origin samurai && restart xledgermate-alpha-hud.service")

    cfg = BotConfig.load()
    st = skynet_status(cfg)
    key = resolve_grok_key(cfg.alpha_grok_api_key)
    print(f"skynet enabled: {st.get('enabled')}")
    print(f"grok key configured: {bool(key)} (source={st.get('key_source', '?')})")
    if key:
        print(f"key hint: {st.get('key_hint', '')}")

    runtime = ROOT / "logs" / "alpha_runtime_state.json"
    if not runtime.is_file():
        print(f"context: skip — {runtime} missing (engine not writing state yet)")
        return 1 if not has_acc else 0

    hud = json.loads(runtime.read_text(encoding="utf-8"))
    try:
        ctx = build_skynet_context(hud, operator_config={})
        print(f"context build: OK ({len(ctx)} chars)")
    except Exception as exc:
        print(f"context build: FAIL — {type(exc).__name__}: {exc}")
        return 1

    print("=== If context OK but HUD still fails: hard-refresh browser (Ctrl+Shift+R) ===")
    return 0 if has_acc and key else 1


if __name__ == "__main__":
    raise SystemExit(main())
