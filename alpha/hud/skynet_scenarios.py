"""Condensed scenario playbook for SKYNET context (mirrors ALPHA_TRADERS_MANUAL scenarios)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from alpha.hud.operator_phase import (
    OPERATOR_PHASE_KEY,
    build_operator_phase_playbook,
    phase_user_message_rules,
)
from alpha.hud.operator_market_regime import (
    OPERATOR_MARKET_REGIME_KEY,
    market_regime_user_message_rules,
    normalize_market_regime,
)
from alpha.hud.skynet_knobs import KNOB_ALIASES  # noqa: F401 — re-export for tests/docs

# SKYNET quick-prompt: bot posture vs market tape (HUD Analysis button — keep in sync).
# Developer HUD ships two presets only: Maximize (default) + Unassed (recovery).
REGIME_PRESET_TACTICS = """=== Regime preset tactics (HUD one-click bundles) ===
Maximize (default): scale + bull, 85% XRP target, strength trim ~5% dev then STOP at target, recycle bid below last sell, last-sell ceiling, dip on pullback-from-high (~1.2%) or −24h, bearish TA waived on recycle/dip, powder ceiling ~90 XRP-eq, drawdown-reload only under floor, powder floor 40, 3.5% clips, brackets OFF. Use when: grow XRP count via harvest → recycle powder → dips.
Unassed (recovery only): scale + bull, 88% XRP target, strength gate 0.06, softer sell TA 2.0, reload floor 18 XRP-eq (accumulation not hard-blocked), wide SL 9% / no trail / fixed TP 2.5%. Use when: stranded bag (near 99% XRP, no powder, dead zone / SL factory). Switch back to Maximize once trims + powder recover.
Fit rules:
- Normal soak / bag growth: Maximize. Do not invent legacy presets (walk-away, long-build, stack-growth, bracket-edge are removed).
- Stranded / bricked inventory: Unassed briefly, then Maximize.
- XRP-heavy + bullish rip: harvest on strength when dev≥strength_dev; keep powder floor.
- RLUSD-heavy + constructive bull: deploy on weakness / dip path under Maximize.
- Everything aligned: say so — no preset change needed."""

BAG_GROWTH_ANALYSIS_PROMPT = """Bot vs market — bag growth analysis (PRIMARY prompt):

Compare what the MARKET is doing right now vs what the BOT is doing.

Read from context: decision (+ reason), inventory, structure, technical_analysis, opportunity_watch, accumulation_regime (incl harvest_watch, dip_deploy_watch), reload_regime, bag_growth, risk_capital, realized_bracket_pnl / realized_pnl_24h, open_offers, brackets, operator phase, market_regime, and operator_preset_tactics block.

Deliver in plain English:
1) Market read — tape (grind / rip / chop / dip), structure trend/breakout, TA bias and scores, 24h leg if harvest/dip relevant.
2) Bot read — current action and why; active path (weakness / strength / accumulation / harvest / reload / HOLD); inventory gates (buy_block, sell_block, pause); any mismatch with what the market is doing.
3) Bag growth — is posture aligned for long-term XRP stack growth? Use bag_growth (bot-adjusted stack delta, trading_edge_7d) and risk_capital sizing — NOT session MTM alone.
4) Regime preset fit — compare effective knobs to Maximize (default harvest loop) or Unassed (recovery only). Recommend Maximize, Unassed, stay, or manual knobs — with clear when/why. Do not invent removed presets.
5) Verdict — either say clearly that everything is well-aligned and no changes are needed, OR give 1–3 specific optimizations (preset name and/or operator knobs).

Judge bleed from realized bracket P&L (tp_exits / sl_exits), not session P&L. Output suggested_changes only when clearly warranted; empty array is OK if posture is perfect. Be direct and conversational."""


def build_regime_preset_tactics_block() -> str:
    """SKYNET context — when to use Maximize vs Unassed presets."""
    return REGIME_PRESET_TACTICS


def build_scenario_playbook() -> str:
    """Compact operator playbook for SKYNET (keep under ~4k chars)."""
    return """=== Scenario playbook (A–R) ===
Map decision.reason + inventory to a scenario, then suggest knob bundles from presets below.

Coupling rules:
- buy_limit_offset_pct >= min_edge_threshold_pct always.
- STICKY bids: stale_max_drift > buy_offset + spread (~0.10%). Example offset 0.12 → drift 0.35.
- CHASE bids: stale_max_drift ≈ buy_offset (expect mid_passed_entry cancel/replace).
- Size ≈ portfolio_xrp_equiv × (risk_per_trade_pct/100); check market_conditions recommended_max_buy_xrp.
- Limit buys fill when best ask <= bid, NOT when mid crosses entry.

A — Bid left behind (uptrend): offset 0.12, min_edge 0.08, drift 0.35, max_pending 1.
B — Patient sniper: offset 0.25–0.35, drift ≈ offset, max_pending 1–2.
C — Ladder clutter: drift 0.15, max_pending 1–3, stale on.
D — edge_below_threshold: raise offset OR lower min_edge.
E — Downtrend knife-catching: weakness↑, ta_min_buy↑, sl_cooldown↑, risk↓, offset↑.
F — Chop / more fills: offset 0.08–0.12, min_edge 0.05–0.08, weakness 0.03–0.04.
G — Entry keeps moving: drift 0.35–0.50, max_pending 1, max_age 0; NOT drift≈offset.
H — Small size (~13 RLUSD @ ~584 XRP): raise risk_per_trade_pct (2→3→4%); not offset.
I — RLUSD-heavy sell_block: normal; buys when dev≤−weakness; no strength sells until less RLUSD-heavy.
J — ta_buy_blocked / bearish: lower ta_min_buy or ta_weight; or wait.
K — post_sl_* re-entry: sl_cooldown, sl_stabilization, sl_min_ta_score; patient reload.
L — post_tp_* re-entry: tp_cooldown, tp_dip_pct, tp_min_ta_score.
M — balanced dev=: lower weakness to buy OR rely on bull_run/momentum (see opportunity_watch). If chart rips while HOLD, read Opportunity watch card — dip-only gate may be blocking.
U — Bull run / breakout missed: TA bullish + balanced dev — accumulation_regime should be PRIMED/ARMED; enable accumulation (default on), SKYNET regime Bull, check re-entry blockers; do NOT silently HOLD without explaining watch state.
V — Accumulation regime ARMED/EXECUTING: alpha_accumulation_buy_offset_pct ~0.06, alpha_accumulation_stale_drift_pct ~0.08 (chase), alpha_accumulation_max_pending_buys 2–3, alpha_accumulation_risk_boost 1.5, alpha_accumulation_bypass_reentry true. Do NOT tighten to dip-only or max_pending=1 unless operator asks defense.
W — RLUSD reload (post-run CHOP): alpha_reload_min_rlusd_deploy_xrp_equiv ~45, alpha_reload_sell_offset_pct ~0.06, sell in consolidation not rip. blocks_accumulation until floor met — fund then bid. Do NOT strength-sell into active breakout; wait for reload WATCHING→ARMED.
X — Drawdown reload: only when powder is UNDER the floor. If powder is already fat, do NOT sell more into a dump — use dip/recycle. Tune only_below_floor stays true on Maximize.
Y — Swing harvest (UP-leg turn): trim when heavy, stop at target, max 1 pending sell. On fill → recycle bid below that sell. ONLY on positive 24h legs — never on red 24h.
Z — Dip deploy: arm on pullback-from-24h-high (~1.2%) OR −24h net, plus bounce off low. Bearish TA is waived on this path. Last-sell ceiling still blocks chase-higher.
AA — Idle powder (301 RLUSD, 0 bids, under target): powder_ceiling should fire. Check recycle pending, last_sell_ceiling, dip_waive_bearish_ta, pullback arm. Do not recommend waiting for a −2% 24h crash.
N — Pending bid no fill: passive limit; lower offset or wait for ask to hit bid.
O — XRP-heavy strength sells: strength_deviation, sell_limit_offset, ta_min_sell.
P — kill_switch / pause_bids / preflight: fix risk first, do not crank aggression.
Q — ta_warming_up: wait or ta_weight=0 advisory.
R — insufficient_ask_depth: book health, not risk knob.

Preset — sticky + ~26 RLUSD @ ~580 XRP portfolio:
  alpha_risk_per_trade_pct=4.0, alpha_buy_limit_offset_pct=0.12, alpha_min_edge_threshold_pct=0.08,
  alpha_stale_pending_buy_max_drift_pct=0.35, alpha_max_pending_buys=1,
  alpha_stale_pending_buy_max_age_seconds=0, alpha_cycle_interval_seconds=20

""" + build_operator_phase_playbook() + """

Natural language → keys: "stickier"→drift↑; "bigger orders"/"26 RLUSD"→risk_per_trade_pct;
"one bid"→max_pending_buys=1; "faster cycles"→cycle_interval_seconds↓; "eager fills"→offset↓.
When operator states desired settings in their prompt, output suggested_changes implementing them.
"""


def infer_scenario_hints(
    *,
    decision_reason: str = "",
    inventory: Optional[Dict[str, Any]] = None,
    reentry: Optional[Dict[str, Any]] = None,
    stale_snapshot: Optional[Dict[str, Any]] = None,
    opportunity_watch: Optional[Dict[str, Any]] = None,
    accumulation_regime: Optional[Dict[str, Any]] = None,
    reload_regime: Optional[Dict[str, Any]] = None,
    drawdown_reload: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Heuristic scenario letters for SKYNET (non-exhaustive)."""
    reason = (decision_reason or "").lower()
    inv = inventory or {}
    hints: List[str] = []
    ow = opportunity_watch or {}
    acc = accumulation_regime or {}
    rel = reload_regime or {}
    dd = drawdown_reload or {}
    hw = acc.get("harvest_watch") if isinstance(acc.get("harvest_watch"), dict) else {}
    dip = acc.get("dip_deploy_watch") if isinstance(acc.get("dip_deploy_watch"), dict) else {}
    dev = inv.get("deviation")
    label = str(inv.get("label") or "")

    if "edge_below" in reason or "edge" in reason and "threshold" in reason:
        hints.append("D")
    if "post_sl" in reason or "reentry_sl" in reason:
        hints.append("K")
    if "post_tp" in reason or "reentry_tp" in reason:
        hints.append("L")
    if "ta_buy_blocked" in reason or "ta_warming" in reason:
        hints.append("J" if "ta_buy" in reason else "Q")
    if "ta_warming" in reason:
        hints.append("Q")
    if "balanced dev" in reason:
        hints.append("M")
        if ow.get("state") in ("watching", "armed", "blocked"):
            hints.append("U")
    if acc.get("armed") or acc.get("phase") in ("armed", "executing", "blocked"):
        hints.append("V")
    if rel.get("armed") or rel.get("phase") in ("armed", "executing", "watching"):
        hints.append("W")
    if rel.get("blocks_accumulation"):
        hints.append("W")
    if dd.get("armed") or dd.get("phase") in ("watching", "armed", "executing", "capped"):
        hints.append("X")
    if "drawdown_reload" in reason:
        hints.append("X")
    if hw.get("phase") in ("watching", "armed", "executing"):
        hints.append("Y")
    if dip.get("phase") in ("watching", "armed"):
        hints.append("Z")
    if "harvest_trim" in reason:
        hints.append("Y")
    if "dip_deploy" in reason:
        hints.append("Z")
    if ow.get("state") in ("armed", "watching"):
        hints.append("U")
    if "max_pending_buys" in reason:
        over = int((stale_snapshot or {}).get("over_cap_count") or 0)
        if over > 0:
            hints.append("C")
        elif dev is not None and float(dev) < -0.05:
            hints.append("I")
    if "insufficient_ask_depth" in reason:
        hints.append("R")
    if "kill_switch" in reason or "pause_bids" in reason or "preflight" in reason:
        hints.append("P")
    if "sell_blocked" in reason or label in ("heavy_rlusd", "rlusd_heavy"):
        if dev is not None and float(dev) < -0.08:
            hints.append("I")
    if stale_snapshot:
        if int(stale_snapshot.get("would_cancel_count") or 0) > 0:
            hints.append("G")
        if int(stale_snapshot.get("over_cap_count") or 0) > 0:
            hints.append("C")

    re = reentry or {}
    if re.get("active") and re.get("in_cooldown"):
        exit_type = str(re.get("exit_type") or "")
        hints.append("K" if exit_type == "sl" else "L" if exit_type == "tp" else "")

    # Dedupe preserving order
    seen: set[str] = set()
    out: List[str] = []
    for h in hints:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out[:6]


def classify_prompt_intent(prompt: str) -> Dict[str, Any]:
    """Lightweight intent tags so SKYNET addresses operator goals, not only auto scenario hints."""
    p = (prompt or "").strip().lower()
    tags: List[str] = []
    if re.search(
        r"\b(bullish|strong\s+buy|buy\s+now|accumulat|deploy\s+rlusd|go\s+long|buy\s+side|load\s+up)\b",
        p,
    ):
        tags.append("bullish_buy")
    if re.search(r"\b(consolidat\w*|base\s+building|range\s+bound|sideways)\b", p):
        tags.append("consolidation")
    if re.search(r"\b(bearish|defensive|reduce\s+risk|stop\s+buying|pause\s+buy)\b", p):
        tags.append("defensive")
    if re.search(r"\b(full\s+summary|summarize|overview|state\s+of\s+the\s+bot)\b", p):
        tags.append("summary_request")
    if re.search(
        r"\b(bot\s+vs\s+market|bag\s+growth\s+analysis|optimize\s+bag\s+growth|everything\s+is\s+well[- ]aligned)\b",
        p,
    ):
        tags.append("bag_growth_analysis")
    if re.search(r"\b(ladder|clutter|stale|cancel.*bid|pending\s+buy)\b", p):
        tags.append("ladder_management")
    settings_cues = bool(
        re.search(
            r"\b(set|configure|apply|change|want|need|make|use|preset|stickier|bigger|smaller|risk\s*\d|offset|drift|pending|cooldown|ta_|reentry)\b",
            p,
            re.I,
        )
    )
    if settings_cues:
        tags.append("settings_request")
    return {"tags": tags, "has_settings_request": settings_cues}


def build_skynet_user_message(
    *,
    user_prompt: str,
    context: str,
    operator_phase: Optional[str] = None,
    market_regime: Optional[str] = None,
    is_follow_up: bool = False,
) -> str:
    """Put operator prompt first; scenarios are reference only."""
    prompt = (user_prompt or "").strip()
    intent = classify_prompt_intent(prompt)
    tags = intent.get("tags") or []

    lines = [
        "=== OPERATOR PROMPT (PRIMARY — your reasoning and summary must address this first) ===",
        prompt or "(empty)",
        "",
        "=== RESPONSE RULES ===",
        "1. Answer the operator prompt directly. Do NOT substitute an unrelated scenario preset.",
        "2. Automated `likely_scenarios` and the playbook below are REFERENCE ONLY — use when they align with operator intent.",
        "3. If operator describes market structure or strategy (e.g. consolidation + bullish → buy), translate that into analysis and knobs.",
    ]
    if is_follow_up:
        lines.extend(
            [
                "6. FOLLOW-UP: prior turns are in the chat history. Continue that thread, but use the FRESH "
                "runtime context in this message for balances, decision, powder, and knobs — not older numbers.",
            ]
        )

    if "bullish_buy" in tags or ("consolidation" in tags and "defensive" not in tags):
        lines.extend(
            [
                "4. BULLISH / BUY intent detected: RLUSD-heavy + TA bullish → favor XRP accumulation knobs "
                "(e.g. alpha_buy_limit_offset_pct↓, alpha_weakness_deviation↓, alpha_ta_min_buy_score↓ if blocking, "
                "alpha_max_pending_buys≥1 to allow entries).",
                "   Do NOT tighten alpha_stale_pending_buy_max_drift_pct or cut max_pending unless operator asked to clear ladder clutter.",
            ]
        )
    elif "ladder_management" in tags:
        lines.append(
            "4. LADDER intent: address stale pending / max_pending using playbook scenarios G or C as appropriate."
        )
    elif "defensive" in tags:
        lines.append(
            "4. DEFENSIVE intent: prioritize capital protection — risk↓, cooldowns↑, patience on re-entry."
        )
    elif "summary_request" in tags:
        lines.append(
            "4. SUMMARY intent: structured state overview first; suggested_changes only if clearly warranted."
        )
    elif "bag_growth_analysis" in tags:
        lines.extend(
            [
                "4. BAG GROWTH ANALYSIS intent: compare market tape vs bot posture first (not ladder clutter by default).",
                "   Include regime preset fit: Maximize (default) vs Unassed (recovery) only (operator_preset_tactics in context).",
                "   End with an explicit verdict: either (a) everything is well-aligned — no changes needed, with brief why, "
                "or (b) 1–3 concrete optimizations (preset recommendation and/or knob changes).",
                "   Use bag_growth, risk_capital, harvest/dip/reload blocks; judge bleed from realized bracket P&L only.",
                "   Do not invent removed presets (walk-away / long-build / stack-growth / bracket-edge).",
            ]
        )

    if intent.get("has_settings_request"):
        lines.append(
            "5. Operator requested specific settings — output concrete suggested_changes (allowlist keys), not prose only."
        )
    else:
        lines.append(
            "5. Include suggested_changes when knob adjustments serve operator goals; empty array is OK if HOLD is correct."
        )

    phase = operator_phase
    if phase is None and OPERATOR_PHASE_KEY + "=" in context:
        for line in context.splitlines():
            if line.startswith("phase="):
                phase = line.split("=", 1)[1].strip().split()[0]
                break
    lines.extend(phase_user_message_rules(phase or "trust"))

    regime = market_regime
    if regime is None and OPERATOR_MARKET_REGIME_KEY + "=" in context:
        for line in context.splitlines():
            if line.startswith("market_regime="):
                regime = line.split("=", 1)[1].strip().split()[0]
                break
    lines.extend(market_regime_user_message_rules(regime or "neutral"))

    lines.extend(["", "=== RUNTIME CONTEXT (secondary) ===", context])
    return "\n".join(lines)
