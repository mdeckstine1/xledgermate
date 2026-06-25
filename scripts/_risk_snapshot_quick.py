"""Risk/deploy snapshot for VPS."""
from __future__ import annotations

import json
from pathlib import Path

from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, effective_config_snapshot
from config.settings import BotConfig


def main() -> None:
    cfg = apply_overrides(BotConfig.load(), OperatorRuntimeStore().load_overrides())
    ov = OperatorRuntimeStore().load_overrides()
    snap = effective_config_snapshot(cfg, ov)
    print("=== RISK / DEPLOY SNAPSHOT ===")
    keys = [
        "dry_run", "trading_enabled", "inventory_target_xrp_ratio", "inventory_target_xrp_pct",
        "alpha_risk_per_trade_pct", "alpha_base_order_size_xrp", "alpha_max_pending_buys",
        "alpha_weakness_deviation", "alpha_buy_limit_offset_pct", "initial_stop_loss_pct",
        "take_profit_rr", "bracket_trailing_enabled", "trailing_step_pct",
        "alpha_reentry_sl_cooldown_cycles", "max_drawdown_pct", "alpha_cycle_interval_seconds",
    ]
    for k in keys:
        if k in snap:
            print(f"  {k}: {snap[k]}")
    print(f"  risk_capital_xrp: {cfg.risk_capital_xrp}")
    print(f"  risk_capital_rlusd: {cfg.risk_capital_rlusd}")
    act = Path("logs/alpha_activity.jsonl")
    if act.is_file():
        lines = act.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            print("\n=== LAST 5 CYCLES ===")
            for line in lines[-5:]:
                try:
                    e = json.loads(line)
                    print(f"  {e.get('ts','')[:19]} {e.get('decision')} | {e.get('reason','')[:80]}")
                except json.JSONDecodeError:
                    pass
    br = Path("logs/alpha_brackets.json")
    if br.is_file():
        data = json.loads(br.read_text())
        recs = data if isinstance(data, list) else data.get("records", [])
        active = [r for r in recs if r.get("state") == "bracket_active"]
        pending = [r for r in recs if r.get("state") == "pending_buy"]
        print(f"\n=== BRACKETS active={len(active)} pending_buys={len(pending)} total_records={len(recs)} ===")


if __name__ == "__main__":
    main()
