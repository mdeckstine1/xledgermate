#!/usr/bin/env python3
"""Read-only live performance review from VPS logs/state."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(".")
LOGS = ROOT / "logs"


def load_json(path: Path, default=None):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def main() -> None:
    state = load_json(LOGS / "alpha_runtime_state.json", {}) or {}
    session = load_json(LOGS / "alpha_session.json", {}) or {}
    week = load_json(LOGS / "alpha_bag_week.json", {}) or {}
    overrides = load_json(LOGS / "alpha_overrides.json", {}) or {}
    deposits = load_json(LOGS / "operator_deposits.json", {}) or {}
    agent = load_json(LOGS / "alpha_skynet_agent.json", {}) or {}

    bag = state.get("bag_growth") or {}
    inv = state.get("inventory") or {}
    risk = state.get("risk") or {}
    decision = state.get("decision") or {}
    acc = state.get("accumulation_regime") or {}
    reload = state.get("reload_regime") or {}
    harvest = (acc.get("harvest_watch") or acc.get("harvest") or {})
    dip = (acc.get("dip_deploy_watch") or acc.get("dip") or {})
    brackets = state.get("brackets") or {}
    bsum = brackets.get("summary") or {}
    realized = state.get("realized_pnl_24h") or {}
    book = state.get("book") or {}
    ta = state.get("technical_analysis") or {}
    opp = state.get("opportunity_watch") or {}
    rc = state.get("risk_capital") or {}
    cfg = state.get("config_effective") or {}
    offers = state.get("open_offers") or []

    print("=== LIVE SNAPSHOT ===")
    print(f"updated: {state.get('updated_utc')}")
    print(f"dry_run={state.get('dry_run')} trading={state.get('trading_enabled')} paused={state.get('operator_paused')}")
    print(f"mid={state.get('mid') or book.get('mid')} bid={book.get('best_bid')} ask={book.get('best_ask')}")
    print(f"xrp={state.get('xrp')} rlusd={state.get('rlusd')} portfolio_xrp_eq={state.get('portfolio_xrp_equiv')}")
    print(f"inventory={inv.get('label')} dev={inv.get('deviation')} target={inv.get('target_xrp_ratio')}")
    print(f"decision={decision.get('action')} reason={decision.get('reason')}")
    print(f"session_pnl={risk.get('session_pnl_xrp')} dd={risk.get('drawdown_pct')} max_dd={risk.get('max_drawdown_pct')}")
    print(f"kill={risk.get('kill_switch_active')} trading_allowed={risk.get('trading_allowed')}")

    print("\n=== BAG SCOREBOARD ===")
    for k in (
        "portfolio_xrp_equiv",
        "portfolio_rlusd_equiv",
        "baseline_portfolio_xrp",
        "baseline_utc",
        "since_baseline_xrp",
        "since_baseline_bot_xrp",
        "since_baseline_bot_pct",
        "operator_deposits_xrp_equiv",
        "day_delta_xrp",
        "day_delta_pct",
        "week_delta_xrp",
        "week_delta_pct",
        "high_water_portfolio_xrp",
        "off_high_xrp",
        "at_high_water",
        "xrp_stack_delta_bot",
        "xrp_stack_delta_raw",
        "baseline_xrp",
        "xrp",
        "rlusd",
    ):
        print(f"  {k}: {bag.get(k)}")
    edge = bag.get("trading_edge_7d") or {}
    print(f"  trading_edge_7d: {edge}")

    print("\n=== DEPOSITS ===")
    deps = deposits.get("deposits") if isinstance(deposits, dict) else deposits
    if isinstance(deps, list):
        total = 0.0
        for d in deps:
            eq = float(d.get("xrp_equiv") or 0)
            total += eq
            print(f"  {d.get('recorded_utc','')[:19]} xrp={d.get('xrp')} rlusd={d.get('rlusd')} eq={eq:.2f} note={d.get('note')}")
        print(f"  TOTAL deposits_xrp_eq={total:.4f}")
    else:
        print("  (none/unavailable)")

    print("\n=== KEY KNOBS (effective / overrides) ===")
    keys = [
        "alpha_operator_phase",
        "alpha_market_regime",
        "inventory_target_xrp_ratio",
        "alpha_risk_per_trade_pct",
        "alpha_strength_deviation",
        "alpha_weakness_deviation",
        "alpha_buy_limit_offset_pct",
        "alpha_sell_limit_offset_pct",
        "alpha_max_pending_buys",
        "alpha_max_pending_sells",
        "alpha_ta_min_buy_score",
        "alpha_ta_min_sell_score",
        "alpha_brackets_enabled",
        "alpha_reload_min_rlusd_deploy_xrp_equiv",
        "alpha_reload_block_accumulation_until_funded",
        "alpha_accumulation_harvest_move_24h_watch_pct",
        "alpha_accumulation_harvest_pullback_arm_pct",
        "alpha_accumulation_harvest_trim_risk_pct",
        "alpha_accumulation_dip_move_24h_arm_pct",
        "alpha_accumulation_dip_bounce_arm_pct",
        "alpha_bull_run_max_deviation",
        "alpha_accumulation_max_deviation",
    ]
    for k in keys:
        ov = overrides.get(k, "—")
        ef = cfg.get(k, "—")
        print(f"  {k}: eff={ef} ov={ov}")

    print("\n=== REGIMES / WATCHES ===")
    print(f"  accumulation: phase={acc.get('phase')} armed={acc.get('armed')} headline={acc.get('headline')}")
    print(f"  reload: phase={reload.get('phase')} blocks={reload.get('blocks_accumulation')} floor={reload.get('deploy_floor_xrp_equiv') or reload.get('min_rlusd_deploy_xrp_equiv')}")
    print(f"  harvest: { {k: harvest.get(k) for k in list(harvest)[:12]} if harvest else harvest }")
    print(f"  dip: { {k: dip.get(k) for k in list(dip)[:12]} if dip else dip }")
    print(f"  opportunity: state={opp.get('state')} headline={opp.get('headline')}")
    print(f"  ta bias={ta.get('bias')} buy_score={ta.get('buy_score')} sell_score={ta.get('sell_score')}")

    print("\n=== BRACKETS / OFFERS ===")
    print(f"  summary={bsum}")
    print(f"  open_offers_count={len(offers) if isinstance(offers, list) else offers}")
    if isinstance(offers, list):
        for o in offers[:8]:
            print(f"    side={o.get('side') or o.get('offer_side')} price={o.get('price') or o.get('quality_price')} size={o.get('size_xrp') or o.get('taker_gets') or o.get('taker_pays')}")

    print("\n=== RISK CAPITAL ===")
    for k, v in (rc.items() if isinstance(rc, dict) else []):
        print(f"  {k}: {v}")

    print("\n=== AGENT SMITH ===")
    print(f"  enabled={agent.get('agent_enabled')} full={agent.get('full_mode_enabled')}")
    print(f"  last_status={agent.get('last_status') or agent.get('status')}")
    prop = agent.get("last_proposal") or agent.get("proposal") or {}
    if isinstance(prop, dict):
        print(f"  proposal_keys={list(prop.keys())[:20]}")
        changes = prop.get("suggested_changes") or prop.get("changes") or []
        if changes:
            print(f"  suggested_changes={changes[:8]}")

    # Recent decisions from activity / decisions.jsonl
    print("\n=== RECENT DECISIONS (activity tail) ===")
    act_path = LOGS / "alpha_activity.jsonl"
    if act_path.is_file():
        lines = act_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-80:]
        reasons = Counter()
        actions = Counter()
        for line in tail:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = row.get("event") or row.get("type") or row.get("kind") or ""
            if "decision" in str(ev).lower() or row.get("action") or row.get("reason"):
                a = row.get("action") or row.get("decision_action") or ev
                r = row.get("reason") or row.get("detail") or row.get("message") or ""
                actions[str(a)[:40]] += 1
                if r:
                    reasons[str(r)[:80]] += 1
        # also dump last 15 raw compact
        print("  action counts (last ~80 lines):")
        for a, c in actions.most_common(15):
            print(f"    {c:3d} {a}")
        print("  reason counts:")
        for r, c in reasons.most_common(15):
            print(f"    {c:3d} {r}")
        print("  last 12 events:")
        for line in tail[-12:]:
            try:
                row = json.loads(line)
                ts = str(row.get("ts") or row.get("utc") or row.get("timestamp") or "")[:19]
                print(f"    {ts} {row.get('event') or row.get('type')} {row.get('action','')} {str(row.get('reason') or row.get('message') or row.get('detail') or '')[:100]}")
            except json.JSONDecodeError:
                print(f"    {line[:120]}")

    dec_path = LOGS / "decisions.jsonl"
    if dec_path.is_file():
        print("\n=== DECISIONS.JSONL (last 40) ===")
        lines = dec_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        acts = Counter()
        reasons = Counter()
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            a = str(row.get("action") or row.get("decision") or "?")
            r = str(row.get("reason") or "")[:90]
            acts[a] += 1
            reasons[r] += 1
        print("  actions:")
        for a, c in acts.most_common():
            print(f"    {c:3d} {a}")
        print("  reasons:")
        for r, c in reasons.most_common(20):
            print(f"    {c:3d} {r}")
        print("  last 8:")
        for line in lines[-8:]:
            try:
                row = json.loads(line)
                print(f"    {str(row.get('ts') or row.get('utc') or '')[:19]} {row.get('action')} | {str(row.get('reason') or '')[:110]}")
            except json.JSONDecodeError:
                pass

    # Realized / tax-ish
    print("\n=== REALIZED 24H ===")
    print(json.dumps(realized, indent=2, default=str)[:1500])

    # Strength sells / harvest session
    for name in ("alpha_strength_sells.json", "harvest_session.json", "reload_session.json", "accumulation_session.json"):
        p = LOGS / name
        data = load_json(p)
        if data:
            print(f"\n=== {name} ===")
            text = json.dumps(data, indent=2, default=str)
            print(text[:1200])

    print("\n=== WEEK STATE ===")
    print(json.dumps(week, indent=2, default=str))
    print("\n=== SESSION ===")
    print(json.dumps(session, indent=2, default=str)[:800])


if __name__ == "__main__":
    main()
