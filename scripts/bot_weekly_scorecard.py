#!/usr/bin/env python3
"""P3: bot-only weekly scorecard (ex-deposits) for harvest-maximize loop."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from alpha.reporting.bag_growth import build_bag_growth_snapshot, format_bag_growth_telegram_block
    from alpha.reporting.operator_deposits import deposits_snapshot
    from alpha.reporting.realized_pnl import build_realized_pnl_snapshot
    from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
    from config.settings import BotConfig

    logs = ROOT / "logs"
    rt_path = logs / "alpha_runtime_state.json"
    rt = json.loads(rt_path.read_text(encoding="utf-8")) if rt_path.is_file() else {}
    xrp = float(rt.get("xrp") or rt.get("balance_xrp") or 0)
    rlusd = float(rt.get("rlusd") or rt.get("balance_rlusd") or 0)
    mid = float(rt.get("mid") or rt.get("mid_price") or 0)
    if mid <= 0 and xrp > 0 and rlusd > 0:
        mid = 1.0

    bag = build_bag_growth_snapshot(
        xrp=xrp,
        rlusd=rlusd,
        mid_rlusd_per_xrp=mid if mid > 0 else None,
        logs_dir=logs,
        persist_week=False,
        persist_stack_baseline=False,
    )
    dep = deposits_snapshot(logs)
    realized_7d = build_realized_pnl_snapshot(
        logs_dir=logs,
        hours=24.0 * 7,
        mid_rlusd_per_xrp=mid if mid > 0 else None,
        max_recent_exits=5,
    )
    eff = apply_overrides(BotConfig.load(), OperatorRuntimeStore().load_overrides())
    floor = float(getattr(eff, "alpha_reload_min_rlusd_deploy_xrp_equiv", 0) or 0)
    rlusd_xeq = (rlusd / mid) if mid > 0 else 0.0
    target = float(getattr(eff, "inventory_target_xrp_ratio", 0.85) or 0.85)
    port = float(bag.get("portfolio_xrp_equiv") or 0)
    ratio = (xrp / port) if port > 0 else 0.0

    print("=== BOT-ONLY WEEKLY SCORECARD ===")
    print(f"as_of_utc: {datetime.now(tz=timezone.utc).isoformat()}")
    print(f"xrp={xrp:.2f} rlusd={rlusd:.2f} mid={mid:.6f} portfolio_xrp_eq={port:.2f}")
    print(f"xrp_ratio={ratio:.1%} target={target:.0%} powder_xeq={rlusd_xeq:.1f} floor={floor:.0f}")
    print(f"brackets_enabled={getattr(eff, 'alpha_brackets_enabled', None)}")
    print()
    print(format_bag_growth_telegram_block(bag))
    print()
    print(
        f"deposits_logged: count={dep.get('count')} "
        f"xrp={dep.get('total_xrp')} rlusd={dep.get('total_rlusd')} "
        f"xrp_eq={dep.get('total_xrp_equiv')}"
    )
    print(
        f"realized_7d: profit_xrp_eq={realized_7d.get('realized_profit_xrp_equiv')} "
        f"tp={realized_7d.get('tp_exits')} sl={realized_7d.get('sl_exits')} "
        f"buys={realized_7d.get('taxable_buys')} sells={realized_7d.get('taxable_sells')}"
    )
    print()
    print("PASS HEURISTICS:")
    bot_stack = bag.get("xrp_stack_delta_bot")
    bot_port = bag.get("since_baseline_bot_xrp")
    print(f"  powder_ok: {rlusd_xeq + 1e-9 >= floor}")
    print(f"  near_target: {abs(ratio - target) < 0.08}")
    print(f"  bot_xrp_stack_delta: {bot_stack}")
    print(f"  bot_portfolio_delta_xrp_eq: {bot_port}")
    print(f"  core_bag_brackets_off: {not getattr(eff, 'alpha_brackets_enabled', True)}")


if __name__ == "__main__":
    main()
