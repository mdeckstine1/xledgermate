#!/usr/bin/env python3
"""Align Agent Smith with Maximize accumulation doctrine on this host."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha.hud.maximize_preset import MAXIMIZE_AGENT_PATCH
from alpha.hud.skynet_agent import (
    agent_status_payload,
    load_agent_config,
    merge_agent_patch,
    save_agent_config,
)
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, effective_config_snapshot
from config.settings import BotConfig


def main() -> None:
    # Apply Maximize agent patch (guardrails + cadence + enabled)
    cfg, errors = merge_agent_patch(dict(MAXIMIZE_AGENT_PATCH))
    if errors:
        print("merge_errors", errors)
        raise SystemExit(1)

    # Clear stuck run flag and stale July proposal so HUD is not misleading
    cfg["running"] = False
    cfg["latest_proposal"] = None
    # Force next run soon after restart (event/cycle based)
    try:
        rt = json.loads(Path("logs/alpha_runtime_state.json").read_text(encoding="utf-8"))
        cycle = int(rt.get("engine_cycle") or rt.get("cycle_count") or 0)
    except Exception:
        cycle = 0
    cfg["last_run_engine_cycle"] = max(0, cycle - 1)
    cfg["next_run_engine_cycle"] = cycle + int(cfg.get("interval_cycles_min") or 10)
    save_agent_config(cfg)

    base = BotConfig.load()
    ov = OperatorRuntimeStore().load_overrides()
    eff = apply_overrides(base, ov)
    snap = effective_config_snapshot(eff, ov)

    print("=== AGENT ALIGNED TO MAXIMIZE ===")
    st = agent_status_payload()
    for k in (
        "agent_enabled",
        "full_mode_enabled",
        "interval_cycles_min",
        "interval_cycles_max",
        "running",
        "next_run_engine_cycle",
        "last_run_engine_cycle",
    ):
        print(f"  {k}={st.get(k)}")
    gr = st.get("guardrails") or {}
    print("  risk_pct", gr.get("alpha_risk_per_trade_pct"))
    print("  target_pct", gr.get("inventory_target_xrp_pct"))
    print("  strength_dev", gr.get("alpha_strength_deviation"))
    print("  reload_floor", gr.get("alpha_reload_min_rlusd_deploy_xrp_equiv"))
    print("  max_changes", gr.get("max_changes_per_cycle"))
    print("  latest_proposal_cleared", st.get("latest_proposal") is None)
    print("=== BOT STILL ===")
    print("  target", snap.get("inventory_target_xrp_ratio"))
    print("  brackets", snap.get("alpha_brackets_enabled"))
    print("  strength", snap.get("alpha_strength_deviation"))
    print("  risk", snap.get("alpha_risk_per_trade_pct"))
    print("  powder_floor", snap.get("alpha_reload_min_rlusd_deploy_xrp_equiv"))
    print("  phase", ov.get("alpha_operator_phase"), "regime", ov.get("alpha_operator_market_regime"))
    print("OK")


if __name__ == "__main__":
    main()
