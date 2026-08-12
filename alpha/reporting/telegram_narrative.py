"""Alpha Telegram narrative reports — stack-first story (pulse / daily / weekly)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from alpha.reporting.bag_growth import build_bag_growth_snapshot

Period = Literal["pulse", "daily", "weekly"]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _sign(n: float, digits: int = 2) -> str:
    return f"{n:+.{digits}f}"


def _market_story(state: Dict[str, Any], bag: Dict[str, Any]) -> str:
    mid = _f(state.get("mid") or bag.get("mid_rlusd_per_xrp"))
    ta = state.get("technical_analysis") or {}
    bias = str(ta.get("bias") or "n/a")
    buy = ta.get("buy_score")
    sell = ta.get("sell_score")

    acc = state.get("accumulation_regime") or {}
    harvest = acc.get("harvest_watch") if isinstance(acc.get("harvest_watch"), dict) else {}
    dip = acc.get("dip_deploy_watch") if isinstance(acc.get("dip_deploy_watch"), dict) else {}
    # Also accept top-level blocks if export flattens them
    if not harvest and isinstance(state.get("harvest_watch"), dict):
        harvest = state["harvest_watch"]
    if not dip and isinstance(state.get("dip_deploy_watch"), dict):
        dip = state["dip_deploy_watch"]

    rolling: Dict[str, Any] = {}
    for block in (dip, harvest):
        r = block.get("rolling") if isinstance(block, dict) else None
        if isinstance(r, dict) and r.get("move_pct") is not None:
            rolling = r
            break

    move_24h = rolling.get("move_pct")
    move_s = ""
    if move_24h is not None:
        try:
            m = float(move_24h)
            if m >= 1.5:
                tape = "up-leg / constructive"
            elif m <= -1.5:
                tape = "down-leg / soft"
            elif abs(m) < 0.5:
                tape = "quiet grind / chop"
            else:
                tape = "mild drift"
            move_s = f"24h mid move {_sign(m, 2)}% — {tape}. "
        except (TypeError, ValueError):
            pass

    h_phase = str(harvest.get("phase") or "idle")
    d_phase = str(dip.get("phase") or "idle")
    h_bit = "Harvest idle" if str(h_phase).lower() in ("idle", "off", "") else f"Harvest {h_phase}"
    d_bit = "dip idle" if str(d_phase).lower() in ("idle", "off", "") else f"dip {d_phase}"

    scores = ""
    if buy is not None or sell is not None:
        try:
            scores = f" TA buy/sell {float(buy or 0):.1f}/{float(sell or 0):.1f}."
        except (TypeError, ValueError):
            scores = ""

    mid_s = f"{mid:.4f}" if mid > 0 else "n/a"
    return (
        f"Mid {mid_s} RLUSD/XRP. {move_s}"
        f"Bias {bias}.{scores} {h_bit}; {d_bit}."
    ).strip()


def _bot_story(state: Dict[str, Any], bag: Dict[str, Any]) -> str:
    decision = state.get("decision") or {}
    action = str(decision.get("action") or "hold").lower()
    reason = str(decision.get("reason") or "").strip()
    inv = state.get("inventory") or {}
    label = inv.get("label") or "?"
    dev = _f(inv.get("deviation"))
    target = _f(inv.get("target_xrp_ratio") or 0.85)
    powder_rlusd = _f(state.get("rlusd") or bag.get("rlusd"))
    mid = _f(state.get("mid") or bag.get("mid_rlusd_per_xrp"))
    powder_xeq = powder_rlusd / mid if mid > 0 else 0.0
    reload = state.get("reload_regime") or {}
    floor = _f(reload.get("deploy_floor_xrp_equiv") or reload.get("min_rlusd_deploy_xrp_equiv") or 40.0)
    offers = state.get("open_offers") or []
    n_offers = len(offers) if isinstance(offers, list) else int(state.get("open_offers_count") or 0)
    paused = bool(state.get("operator_paused"))
    kill = bool((state.get("risk") or {}).get("kill_switch_active"))

    parts: List[str] = []
    if kill:
        parts.append("Kill switch is ACTIVE — trading blocked.")
    elif paused:
        parts.append("Operator paused.")
    else:
        if action in ("hold", "HOLD"):
            if "max_pending_sells" in reason:
                parts.append(
                    "Holding with sell slots full (max pending sells) — "
                    "stale-ask cancel should free zombies; watch for trims next."
                )
            elif "balanced" in reason.lower():
                parts.append("Holding near balance — no forced trade.")
            else:
                parts.append(f"Holding ({reason or 'no edge / gates'}).")
        elif "ask" in action or "sell" in action:
            parts.append(f"Selling / trimming ({reason or action}).")
        elif "bid" in action or "buy" in action:
            parts.append(f"Buying / deploying ({reason or action}).")
        else:
            parts.append(f"Action {action}: {reason or '—'}.")

    heavy_pp = (dev - 0.0) * 100.0  # deviation already vs target
    # deviation is absolute off target ratio
    parts.append(
        f"Inventory {label}, {_sign(dev * 100, 1)} pp vs target {target * 100:.0f}% XRP."
    )
    if powder_xeq + 1e-9 >= floor:
        parts.append(f"Powder healthy ~{powder_xeq:.0f} XRP-eq (floor {floor:.0f}).")
    else:
        parts.append(f"Powder light ~{powder_xeq:.0f} XRP-eq under floor {floor:.0f}.")
    if n_offers:
        parts.append(f"{n_offers} open offer(s) on the book.")
    return " ".join(parts)


def build_recommendations(
    state: Dict[str, Any],
    bag: Dict[str, Any],
    *,
    agent: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Sparse, actionable recs only — empty list means omit section."""
    recs: List[str] = []
    risk = state.get("risk") or {}
    decision = state.get("decision") or {}
    reason = str(decision.get("reason") or "")
    reload = state.get("reload_regime") or {}
    inv = state.get("inventory") or {}
    dev = _f(inv.get("deviation"))
    powder_rlusd = _f(state.get("rlusd") or bag.get("rlusd"))
    mid = _f(state.get("mid") or bag.get("mid_rlusd_per_xrp"))
    powder_xeq = powder_rlusd / mid if mid > 0 else 0.0
    floor = _f(reload.get("deploy_floor_xrp_equiv") or 40.0)

    if risk.get("kill_switch_active"):
        recs.append("Clear kill switch only after you understand the drawdown trigger.")
    if state.get("operator_paused"):
        recs.append("Trading is paused — resume from HUD when ready.")
    if "max_pending_sells" in reason:
        recs.append(
            "Sell slots full — confirm stale strength-sell cancel is on; "
            "cancel far asks if stalls persist."
        )
    if powder_xeq + 1e-9 < floor and dev >= _f(state.get("config_effective", {}).get("alpha_strength_deviation") or 0.05):
        recs.append("Heavy inventory and powder under floor — prefer trims/funding before new bids.")
    if bag.get("at_high_water") is False and bag.get("off_high_xrp") is not None:
        off = _f(bag.get("off_high_xrp"))
        if off <= -15.0:
            recs.append(
                f"Bag {_sign(off, 1)} XRP-eq off ATH — check mid vs stack; avoid panic knobs on MTM alone."
            )

    agent = agent or {}
    if agent.get("agent_enabled"):
        rem = agent.get("budget_remaining")
        if rem is not None and int(rem) == 0 and int(agent.get("daily_call_budget") or 0) > 0:
            recs.append("Agent Smith daily call budget empty until UTC midnight (manual Run still works).")
        prop = agent.get("latest_proposal") or {}
        safe = prop.get("safe_changes") or []
        if safe and not prop.get("auto_applied"):
            keys = ", ".join(str(c.get("key") or "") for c in safe[:3] if c.get("key"))
            if keys:
                recs.append(f"Agent Smith has {len(safe)} safe suggestion(s) pending review ({keys}).")

    # Cap noise
    return recs[:4]


def _stack_line(bag: Dict[str, Any]) -> str:
    stack = bag.get("xrp_stack_delta_bot")
    if stack is None:
        stack = bag.get("xrp_stack_delta_raw")
    if stack is None:
        return "XRP stack: baseline not set yet."
    now_x = bag.get("xrp")
    base_x = bag.get("baseline_xrp")
    extra = ""
    if now_x is not None and base_x is not None:
        extra = f" (now {_f(now_x):.1f} · baseline {_f(base_x):.1f})"
    return f"Bot stack since baseline: {_sign(_f(stack), 2)} XRP coins{extra}."


def _value_lines(bag: Dict[str, Any], *, detail: bool) -> List[str]:
    total = bag.get("portfolio_xrp_equiv")
    bot = bag.get("since_baseline_bot_xrp")
    if bot is None:
        bot = bag.get("since_baseline_xrp")
    day = bag.get("day_delta_xrp")
    week = bag.get("week_delta_xrp")
    lines = []
    if total is not None:
        rlusd_eq = bag.get("portfolio_rlusd_equiv")
        tail = f" (≈ {_f(rlusd_eq):.0f} RLUSD)" if rlusd_eq is not None else ""
        lines.append(f"TOTAL BAG: {_f(total):.2f} XRP-eq{tail}")
    if bot is not None:
        lines.append(f"BOT ADDED (value, ex deposits): {_sign(_f(bot), 2)} XRP-eq")
    if detail:
        if day is not None:
            lines.append(f"Today: {_sign(_f(day), 2)} · Week: {_sign(_f(week or 0), 2)}")
        off = bag.get("off_high_xrp")
        if bag.get("at_high_water"):
            lines.append("vs ATH: at high")
        elif off is not None:
            lines.append(f"vs ATH: {_sign(_f(off), 2)} off high")
        dep = _f(bag.get("operator_deposits_xrp_equiv"))
        if dep > 0:
            lines.append(f"Deposits logged: {dep:.1f} XRP-eq (stripped from bot metrics)")
    else:
        bits = []
        if day is not None:
            bits.append(f"today {_sign(_f(day), 2)}")
        if week is not None:
            bits.append(f"week {_sign(_f(week), 2)}")
        if bits:
            lines.append(" · ".join(bits))
    return lines


def build_alpha_narrative_report(
    *,
    state: Dict[str, Any],
    logs_dir: str | Path = "logs",
    period: Period = "daily",
    now: Optional[datetime] = None,
    hud_url: str = "",
    agent: Optional[Dict[str, Any]] = None,
    persist_week: bool = False,
) -> str:
    """
    Stack-first narrative for Telegram.

    period:
      pulse  — short hourly-style briefing
      daily  — full story
      weekly — longer stack chapter
    """
    now = now or datetime.now(tz=timezone.utc)
    logs = Path(logs_dir)
    bag = build_bag_growth_snapshot(
        xrp=_f(state.get("xrp")),
        rlusd=_f(state.get("rlusd")),
        mid_rlusd_per_xrp=state.get("mid"),
        logs_dir=logs,
        now=now,
        persist_week=persist_week,
        persist_stack_baseline=False,
    )

    mode = "DRY-RUN" if state.get("dry_run", True) else "LIVE"
    posture = state.get("posture") or "—"
    title = {
        "pulse": "XLedgerMate — Hourly pulse",
        "daily": "XLedgerMate — Daily bag story",
        "weekly": "XLedgerMate — Weekly stack chapter",
    }.get(period, "XLedgerMate — Bag story")

    lines: List[str] = [
        title,
        f"{now.strftime('%Y-%m-%d %H:%M')} UTC · {mode} · {posture}",
        "",
    ]

    if period == "pulse":
        lines.append("STACK")
        lines.append(f"  {_stack_line(bag)}")
        for vl in _value_lines(bag, detail=False):
            lines.append(f"  {vl}")
        decision = state.get("decision") or {}
        lines.append("")
        lines.append(
            f"BOT  {(decision.get('action') or 'hold')} — {(decision.get('reason') or '—')[:80]}"
        )
        inv = state.get("inventory") or {}
        lines.append(
            f"MKT  mid {_f(state.get('mid')):.4f} · {inv.get('label', '?')} "
            f"dev={_sign(_f(inv.get('deviation')) * 100, 1)}pp"
        )
        recs = build_recommendations(state, bag, agent=agent)
        if recs:
            lines.append("")
            lines.append("NOTE  " + recs[0])
        if (state.get("risk") or {}).get("kill_switch_active"):
            lines.append("KILL  active")
    else:
        lines.append("THE STACK")
        lines.append(f"  {_stack_line(bag)}")
        if period == "weekly":
            lines.append(
                "  Coin count is the Maximize scorecard — deposits stripped from the bot number."
            )
        lines.append("")
        lines.append("THE BAG")
        for vl in _value_lines(bag, detail=True):
            lines.append(f"  {vl}")
        xrp = _f(state.get("xrp") or bag.get("xrp"))
        rlusd = _f(state.get("rlusd") or bag.get("rlusd"))
        lines.append(f"  Holdings: {xrp:.2f} XRP + {rlusd:.2f} RLUSD powder")
        lines.append("")
        lines.append("THE MARKET")
        lines.append(f"  {_market_story(state, bag)}")
        lines.append("")
        lines.append("THE BOT")
        lines.append(f"  {_bot_story(state, bag)}")

        if period == "weekly":
            lines.append("")
            lines.append("THE WEEK")
            w = bag.get("week_delta_xrp")
            wx = bag.get("week_xrp_delta")
            if w is not None:
                lines.append(
                    f"  Portfolio value this week (Mon UTC): {_sign(_f(w), 2)} XRP-eq"
                    + (f" ({_sign(_f(bag.get('week_delta_pct') or 0), 2)}%)" if bag.get("week_delta_pct") is not None else "")
                )
            if wx is not None:
                lines.append(f"  Raw XRP coin Δ this week: {_sign(_f(wx), 2)} (includes any deposits)")
            edge = bag.get("trading_edge_7d") or {}
            if edge.get("available"):
                lines.append(
                    f"  Realized bracket edge 7d: {_sign(_f(edge.get('realized_profit_xrp_equiv')), 2)} XRP-eq "
                    f"(TP {edge.get('tp_exits', 0)} / SL {edge.get('sl_exits', 0)}) — core bag often brackets-off."
                )

        recs = build_recommendations(state, bag, agent=agent)
        lines.append("")
        if recs:
            lines.append("RECOMMENDATIONS")
            for r in recs:
                lines.append(f"  • {r}")
        else:
            lines.append("RECOMMENDATIONS")
            lines.append("  No action needed — soak.")

    hud = (hud_url or "").strip()
    if hud:
        lines.extend(["", f"HUD: {hud}"])
    return "\n".join(lines)


def load_alpha_state(logs_dir: Path) -> Dict[str, Any]:
    return _load_json(logs_dir / "alpha_runtime_state.json")


def load_agent_for_recs(logs_dir: Path) -> Dict[str, Any]:
    """Lightweight agent snapshot for recs (no package agent load required)."""
    raw = _load_json(logs_dir / "alpha_skynet_agent.json")
    if not raw:
        return {}
    # Budget remaining for recs
    budget = int(raw.get("daily_call_budget") or 0)
    used = int(raw.get("daily_calls_used") or 0)
    remaining = None if budget <= 0 else max(0, budget - used)
    return {
        "agent_enabled": bool(raw.get("agent_enabled")),
        "daily_call_budget": budget,
        "daily_calls_used": used,
        "budget_remaining": remaining,
        "latest_proposal": raw.get("latest_proposal"),
    }
