"""One-shot reorganizer: ALPHA_TRADERS_MANUAL.md by HUD tab/card + scenario appendices."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "ALPHA_TRADERS_MANUAL.md"
DST = ROOT / "docs" / "ALPHA_TRADERS_MANUAL.md"

REGIME_TABLE = """
| Regime | Operator stance |
|--------|-----------------|
| **Bull** | {bull} |
| **Neutral** | {neutral} |
| **Bear** | {bear} |

**Narrative:** {narrative}

**See also:** {seealso}
"""


def card(
    title: str,
    *,
    what: str,
    use: str,
    bull: str,
    neutral: str,
    bear: str,
    narrative: str,
    seealso: str = "—",
) -> str:
    lines = [
        f"#### {title}",
        "",
        f"**What it is:** {what}",
        "",
        f"**How to use it:** {use}",
        "",
        REGIME_TABLE.format(
            bull=bull,
            neutral=neutral,
            bear=bear,
            narrative=narrative,
            seealso=seealso,
        ).strip(),
        "",
    ]
    return "\n".join(lines)


def extract_section(text: str, start_header: str, end_header: str | None) -> str:
    start = text.find(start_header)
    if start < 0:
        return ""
    if end_header:
        end = text.find(end_header, start + len(start_header))
        if end < 0:
            end = len(text)
    else:
        end = len(text)
    return text[start:end].strip()


def scenario_to_appendix(block: str, letter: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    anchor = f"appendix-{letter.lower()}--{slug}"
    out = block.replace(f"### Scenario {letter} — {title}", f"### Appendix {letter} — {title}")
    # Fix internal scenario links to appendix
    out = re.sub(
        r"\]\(#scenario-([a-z])--",
        r"](#appendix-\1--",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"\[Scenario ([A-Z])\]\(#scenario-\1",
        lambda m: f"[Appendix {m.group(1)}](#appendix-{m.group(1).lower()}",
        out,
        flags=re.I,
    )
    if not out.startswith("###"):
        out = f"### Appendix {letter} — {title}\n\n{out}"
    return out.strip() + "\n"


def build_part1() -> str:
    parts: list[str] = []

    parts.append(
        """## Part 1 — HUD guide (by tab, then card)

Nav order: **Live · TA · Brackets · Open offers · Reports · Activity · PRO · SKYNET · Config**

Every card below uses the same lens:

- **What it is** — what you are looking at on screen
- **How to use it** — when to glance, when to act
- **Bull / Neutral / Bear** — how tape regime should color your reading (SKYNET **market regime** mirrors this for advice)
- **Narrative** — one sentence of operator story
- **See also** — deep-dive **Appendices** at the end of this manual

---"""
    )

    # Always visible
    parts.append(
        """### Always visible — header & sidebar

The ticker and left rail update every **~1 second**. They are your pulse when you are not on the Live tab.

"""
        + card(
            "Ticker & mode badges",
            what="Top bar: version, network, LIVE/dry-run, posture, pause/kill badges, freshness.",
            use="First glance on login. **Kill** or **Pause** badges mean stop tuning knobs — fix state first.",
            bull="LIVE + no kill + inventory drifting toward target — let it run.",
            neutral="Chop: frequent HOLD reasons are normal if Decision explains them.",
            bear="Kill lit, drawdown climbing, or pause active — no aggression until cleared.",
            narrative="You open the HUD at 7am; the ticker says LIVE and fresh — coffee first, then Decision.",
            seealso="[Appendix P](#appendix-p--kill-switch-drawdown-or-pause)",
        )
        + card(
            "Portfolio, inventory & P&L",
            what="Sidebar: mid, XRP/RLUSD balances, XRP %, deviation label, drawdown, session P&L, realized 24h.",
            use="**Session P&L** is mark-to-market (can lie after deposits). **Realized 24h** is tax-CSV truth for bleed.",
            bull="Session and realized both positive — optional scale phase on SKYNET.",
            neutral="Session green, realized flat — common in chop; trust realized for edge.",
            bear="Realized bleeding while session flat — open **PRO** replay; expect defensive circuit.",
            narrative="Session says +200 XRP after you funded yesterday — ignore it; read Realized 24h instead.",
            seealso="[Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro) · [Funding changes](#funding-changes-scaling-toward-11k-xrp)",
        )
        + card(
            "Quote age",
            what="How stale the last L1 book patch is.",
            use="Stale >25s — next full book sample is coming; don't panic on one old mid tick.",
            bull="Fresh quotes + rising mid — fills may still be passive-limit slow.",
            neutral="15–25s age is normal between engine cycles.",
            bear="Stale during volatility — wait for fresh book before repricing bids.",
            narrative="Mid flickers but quote age says 18s — the chart line is live, depth card lags one cycle.",
            seealso="[Data speed](#data-speed--what-updates-how-fast)",
        )
    )

    # LIVE TAB
    parts.append(
        """### Live tab

The command center. Decision + Market Conditions + three control decks (**Risk & entry**, **Structure & trailing**, **Re-entry**).

"""
        + card(
            "Decision",
            what="Last engine action (`HOLD`, `PLACE_BID`, `PLACE_ASK`) and the **reason string**.",
            use="**Always read the reason before touching knobs.** It maps 1:1 to an Appendix letter in the cheat table at the end of Part 2.",
            bull="`place_bid` with weakness dev — deployment working.",
            neutral="`hold` with `max_pending_buys` or re-entry gates — patience, not broken.",
            bear="`hold` with `ta_buy_blocked bearish` after SL streak — don't lower offset; see PRO/SKYNET bear.",
            narrative="Decision says `reentry_sl_await_bounce` — the bot is doing what you asked after a stop.",
            seealso="[Why no buys?](#why-no-buys--decision-reason-cheat-sheet) · Appendices **K**, **J**, **D**",
        )
        + card(
            "Book",
            what="Mid and spread from the latest book patch.",
            use="Compare to Brackets **entry** and Market Conditions **best bid/ask** — mid alone doesn't fill limits.",
            bull="Spread tight, mid rising — eager offsets still won't fill until ask trades down.",
            neutral="Typical 8–15 bps spread on RLUSD/XRP mainnet.",
            bear="Wide spread or gap — consider wider offsets and lower size.",
            narrative="Book mid 1.029 but your bid is 1.027 — you are intentionally below the touch.",
            seealso="[Appendix N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill)",
        )
        + card(
            "Structure",
            what="Short HTF trend label + summary from recent mids.",
            use="Context for trailing (**BE**/**BO**) and re-entry stabilization — not a buy button.",
            bull="`breakout_up` — trailing may arm on filled bags.",
            neutral="`neutral` chop — pair with TA bias, not structure alone.",
            bear="`breakout_down` — post-SL re-entry waits for stabilization.",
            narrative="Structure says neutral while TA says bearish — re-entry after SL stays blocked.",
            seealso="[Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload)",
        )
        + card(
            "Brackets summary",
            what="Counts: pending buys, active fixed, SL trail, breakout trail, orphan bids.",
            use="If pending > `max_pending_buys`, expect stale cancels or HOLD — open **Brackets** tab for detail.",
            bull="Active brackets with **BE** flags — winners trailing.",
            neutral="One pending buy, zero active — normal deploy queue.",
            bear="Many pending, none filling — ladder clutter; don't add heat.",
            narrative="Summary says 4 pending but cap is 1 — engine is pruning, not ignoring you.",
            seealso="[Appendix C](#appendix-c--ladder-clutter-many-pending-buys-none-filling)",
        )
        + card(
            "Preflight",
            what="Wallet/trust-line/config readiness summary.",
            use="Must be green before live quoting. Red here beats every knob tweak.",
            bull="Preflight OK — focus on Decision.",
            neutral="—",
            bear="Preflight fail — fix trust line, balance, or config before trading.",
            narrative="You cranked risk to 5% but preflight says trust line missing — nothing will place.",
            seealso="[Appendix P](#appendix-p--kill-switch-drawdown-or-pause)",
        )
        + card(
            "Execution",
            what="Last cycle execution result (bid placed, dry-run skip, etc.).",
            use="Confirms whether the last Decision actually hit the ledger.",
            bull="`place_bid executed` — offer on book; check Brackets.",
            neutral="Skipped due to pause — expected if you paused.",
            bear="Repeated skips with risk allowed — read Decision reason, not Execution alone.",
            narrative="Decision said PLACE_BID but Execution dry_run — you are still in sim mode.",
            seealso="[Config → dry_run](#config-tab)",
        )
        + card(
            "Mid price chart",
            what="Candle history (lagging) + live bid/ask/mid lines (1s poll). Timeframe buttons: 5m–2h.",
            use="Candles lag samples; **live lines** are fresher. Use for context, not exact fill prediction.",
            bull="Higher highs — don't chase with offset↓ unless scale phase earned.",
            neutral="Sideways box — TA gate matters more than chart FOMO.",
            bear="Lower highs — trust phase offsets; PRO/defensive may trip.",
            narrative="Candles look bullish but last three Decision lines say `ta_buy_blocked` — believe Decision.",
            seealso="[TA tab](#ta-tab) · [Appendix A](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind)",
        )
        + card(
            "Market Conditions",
            what="Spread, depth ±1% of mid, max buy size, regime, ATR%, realized vol, DCA lines, cycle timing.",
            use="**Max buy** is the binding clip right now. Depth refreshes each **engine cycle**, not each HUD poll.",
            bull="Deep ask book, max buy at your risk cap — deploy when gates pass.",
            neutral="Regime chop, ATR moderate — default offsets.",
            bear="Thin depth, max buy tiny — don't raise risk%; fix book health first.",
            narrative="Max buy 17.5 XRP — that's 3% of book, not a bug.",
            seealso="[Appendix H](#appendix-h--order-size-stuck-13-rlusd-or-smaller-than-expected) · [Appendix R](#appendix-r--insufficient_ask_depth)",
        )
    )

    # Risk & entry - consolidated card with knob subsections from template
    parts.append(
        """#### Risk & entry (control deck)

**What it is:** The main tuning surface — target allocation, size, edge, bid placement, stale cancel, deferred SL, cycle speed. **Apply** after changes.

**How to use it:** Change **one knob** per soak window. After Apply, watch Decision 10–20 cycles. Cross-check **Market Conditions → Max buy**.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Modest offset (0.12–0.18), `max_pending_buys` 2–3 only after clean realized week; scale SKYNET phase. |
| **Neutral** | Default patient offsets (0.15–0.25), `max_pending_buys` 1–2, sticky drift > offset + spread. |
| **Bear** | Wide offset (0.18+), `max_pending_buys` 1, lower risk%, trust/defensive circuit; no offset chase. |

**Narrative:** You lower offset to catch a rip — fills improve, SLs cluster — PRO trips bear bundle overnight.

**See also:** [Knob coupling](#knob-coupling--change-x-change-y) · Appendices **A–I**, **V**

##### `target_xrp_pct` / `weakness_deviation` / `strength_deviation`

North star XRP share and how far below/above target before buys/sells fire. RLUSD-heavy = below target = buy side eligible.

| Regime | target / weakness |
|--------|-------------------|
| **Bull** | target 80–85%, weakness 0.03–0.04 |
| **Neutral** | target 75–80%, weakness 0.04–0.05 |
| **Bear** | target unchanged; raise weakness 0.06–0.08 (fewer knives) |

##### `risk_per_trade_pct`

Caps bracket size ≈ `% × portfolio` (also leg cap & depth). HUD **Max buy** confirms.

| Regime | Typical |
|--------|---------|
| **Bull** | 2.5–3.5% after trust earned |
| **Neutral** | 0.5–2.5% |
| **Bear** | ≤2.5%; defensive circuit may force min |

##### `min_edge_threshold_pct` ⚠️

Must be **≤ `buy_limit_offset_pct`** or HOLD forever (`edge_below_threshold`). Couple with offset changes.

##### `buy_limit_offset_pct` / `sell_limit_offset_pct`

Distance below mid (buy) or above mid (sell). Main fill vs entry-quality lever.

| Regime | buy offset |
|--------|------------|
| **Bull** | 0.08–0.15 (eager) only if realized P&L healthy |
| **Neutral** | 0.15–0.25 |
| **Bear** | 0.18–0.35 patient |

##### `max_pending_buys` / stale pending buy knobs

`stale_pending_buy_max_drift_pct` must be **> offset + spread** for sticky bids, or ≈ offset to chase. **`mid_passed_entry` trap** — see Appendix G.

##### `deferred_sl_enabled` / `deferred_sl_arm_buffer_pct` ⚠️

XRPL stops below bid cross instantly without deferral. **SL↯** on Brackets = off-ledger stop until arm.

| Regime | deferred SL |
|--------|-------------|
| **Bull** | On; buffer 0–0.1% |
| **Neutral** | On; default buffer 0% |
| **Bear** | On; avoid disabling; widen `initial_stop_loss_pct` instead |

##### `cycle_interval_seconds`

5–60s between engine cycles. Lower = faster stale cancel/replace, more RPC load.

---
"""
    )

    parts.append(
        """#### Structure & trailing (control deck)

**What it is:** Stop/TP distances, trailing enable, breakout/structure lookback — protects filled bags.

**How to use it:** Prove deferred SL before enabling trailing. Watch Brackets **Trail** column (**BE**/**BO**).

| Regime | Stance |
|--------|--------|
| **Bull** | Trailing on, `trailing_step_pct` 1.5–2%, breakout 0.02 |
| **Neutral** | Trailing on after soak; fixed TP/SL first week |
| **Bear** | Trailing off if scratch SL churn; wider `initial_stop_loss_pct` |

**Narrative:** BE flags appear on a rally — then one wick scratches four brackets; scratch tier saves you from 71-cycle SL penalty.

**See also:** [Appendix E](#appendix-e--buying-too-often-in-a-downtrend) · SL mitigations below

Key knobs: `bracket_trailing_enabled`, `trailing_step_pct`, `breakout_pct`, `structure_lookback`, `initial_stop_loss_pct`, `take_profit_pct` / `take_profit_rr`.

---
"""
    )

    parts.append(
        """#### Re-entry after exit (control deck)

**What it is:** Cooldowns and gates after TP/SL before the next buy — anti-churn discipline.

**How to use it:** Read Decision re-entry line. Cooldowns are **non-negotiable** first; then dip/stabilization/TA.

| Regime | Stance |
|--------|--------|
| **Bull** | Shorter TP cooldown/dip; keep SL cooldown meaningful |
| **Neutral** | Default TP 4 / SL 8–15 cycles |
| **Bear** | Long SL cooldown, high `sl_min_ta_score`, deep offsets after damage |

**Narrative:** TP at 1.10 — bot refuses to rebuy at 1.105 because you set `tp_dip_pct` — that's the feature.

**See also:** [Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload) · [Appendix L](#appendix-l--post-tp-re-entry-waiting-for-dip)

#### SL mitigations (sub-panel)

Scratch tier, cluster window, recovery release, post-clear spacing — tame breakeven SL storms without disabling re-entry.

| Knob | Bear tip |
|------|----------|
| `scratch_sl_max_loss_pct` | 0.10–0.15 — more exits count as scratch |
| `scratch_sl_cooldown_cycles` | 3–6 |
| `sl_cluster_window_sec` | 1800+ — cluster doesn't reset timer |
| `recovery_enabled` | on — end cooldown when price recovers |

---
"""
    )

    parts.append(
        """#### Manual actions (control deck)

**What it is:** Pause, resume, cancel all, config reload, dry-run toggle, engine start.

**How to use it:** **Pause** stops new entries; brackets stay. **Cancel all** is nuclear — type `CANCEL_ALL`.

| Regime | Action |
|--------|--------|
| **Bull** | Rarely touch — let brackets work |
| **Neutral** | Pause for manual bracket surgery |
| **Bear** | Pause + review PRO; cancel pending ladder if cluttered |

**Narrative:** You cancel all during a bleed — you keep XRP bags without TP/SL until you fix posture.

**See also:** [Emergency controls](#emergency-controls)

---
"""
    )

    # TA TAB
    parts.append(
        """### TA tab

Technical analysis gate and indicator detail. **TA tuning** sliders at top; indicator cards below.

"""
        + card(
            "TA tuning (`ta_enabled`, `ta_weight`, scores, candle interval)",
            what="Master switch, gate strength, min buy/sell scores, bar size.",
            use="`ta_weight` 0 = advisory; 1 = hard gate. Changing candle interval affects warmup time.",
            bull="weight 0.6–0.8, min_buy 1.2–1.5 — participate in trend.",
            neutral="weight 0.8, min_buy 1.5–2.0 — default chop filter.",
            bear="weight 1.0, min_buy 2.0+, bearish bias blocks — expect HOLD.",
            narrative="You disable TA to force buys in bear tape — you catch the knife; turn it back on.",
            seealso="[Appendix J](#appendix-j--ta-blocking-buys-in-chop) · [Appendix Q](#appendix-q--ta_warming_up--insufficient-history)",
        )
        + card(
            "Status / Bias / Buy / Sell / Breakout scores",
            what="Composite scores and whether each gate passes.",
            use="Mirror Decision `decTa` line on Live tab. Buy gate FAIL = no PLACE_BID when weight=1.",
            bull="buy > min, bias bullish/neutral — gate PASS.",
            neutral="scores flicker 1.2–1.8 — normal chop.",
            bear="bearish bias or sell > buy — gate BLOCK.",
            narrative="Buy score 1.51, min 1.50 — one tick from HOLD forever.",
            seealso="[Appendix J](#appendix-j--ta-blocking-buys-in-chop)",
        )
        + card(
            "RSI / Stochastic / Bollinger / Fibonacci / Signals",
            what="Indicator breakdown and recent signal list.",
            use="Diagnostics when you disagree with composite score. Signals table = last fired rules.",
            bull="Oversold RSI + bullish engulfing — supports buy score.",
            neutral="Mixed signals — trust composite over one indicator.",
            bear="Overbought + bearish bias — don't override with weakness alone.",
            narrative="RSI 28 but bias bearish — structure still down; re-entry waits.",
            seealso="[Appendix J](#appendix-j--ta-blocking-buys-in-chop)",
        )
    )

    # Other tabs
    parts.append(
        """### Brackets tab

Full bracket table: state, mode, entry, size, TP/SL, trail flags, per-row cancel/edit.

**What it is:** Source of truth for **pending buy** vs **active** vs history rows.

**How to use it:** Only **`pending buy`** counts toward cap. **SL↯** = deferred stop. **BE**/**BO** = trailing milestones.

| Regime | Stance |
|--------|--------|
| **Bull** | Watch BE/BO; trail winners |
| **Neutral** | One pending, edit entry with ✎ if needed |
| **Bear** | Cancel excess pending; don't stack ladder |

**Narrative:** JSON file shows 1058 rows; HUD shows 1 pending — believe the HUD State column.

**See also:** [Appendix C](#appendix-c--ladder-clutter-many-pending-buys-none-filling) · [Appendix G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop)

---

### Open Offers tab

Raw XRPL offers (sequence, side, price, size). ✕ cancel, ✎ reprice.

**What it is:** Ledger truth — one row per open offer including non-bracket asks.

**How to use it:** When Brackets and Offers disagree, Offers wins for "what's on chain."

| Regime | Stance |
|--------|--------|
| **Bull** | Expect bid + TP legs on active bags |
| **Neutral** | Single bid typical |
| **Bear** | Many stale bids — prune via Brackets or Cancel all |

**Narrative:** One offer, sequence 12345 — that's your only pending bid.

**See also:** [Appendix N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill)

---

### Reports tab

Cycle report text, tax CSV path, download helpers, transfer index.

**What it is:** Human-readable cycle dump + pointer to `logs/trades_YYYY-MM.csv`.

**How to use it:** Archive monthly CSV for taxes. Cross-check realized P&L vs PRO replay.

| Regime | Stance |
|--------|--------|
| **Bull** | TP rows dominate CSV |
| **Neutral** | Mixed small P&L |
| **Bear** | SL rows cluster — sum `profit_xrp_equiv` |

**Narrative:** Session P&L +200, CSV sum −5 — you were measuring the wrong scoreboard.

**See also:** [Tax & transfer records](#tax--transfer-records) · [Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro)

---

### Activity tab

Reverse-chronological engine events (cycles, cancels, fills, defensive circuit).

**What it is:** Lightweight log tail — faster than SSH for "did stale cancel fire?"

**How to use it:** After Apply, look for `stale_pending_buy_cancelled`, `defensive_circuit`, `place_bid`.

| Regime | Stance |
|--------|--------|
| **Bull** | Regular `place_bid` / fills |
| **Neutral** | Mix HOLD + occasional bid |
| **Bear** | SL cluster in log; `defensive_circuit_activated` |

**Narrative:** Activity every 34s says hold — that's one engine cycle, not a freeze.

**See also:** [Appendix G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop)

---

### PRO tab

**Alpha Replay**, **auto-defensive circuit**, **treasury placeholder**.

"""
        + card(
            "Alpha Replay",
            what="Rolling TP/SL, realized P&L, scratch SLs, verdict (`healthy`/`sl_heavy`/`bleeding`/`churn`).",
            use="Pick window (14h default). Judge bleed here — not Session P&L.",
            bull="TP ≥ SL, verdict healthy — optional release defensive.",
            neutral="Mixed — watch trend over 48h.",
            bear="sl_heavy / bleeding — expect or confirm defensive ACTIVE.",
            narrative="63 SL, 0 TP — verdict sl_heavy; you didn't need to wait for Session P&L to tell you.",
            seealso="[Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro)",
        )
        + card(
            "Auto-defensive circuit",
            what="Auto bear bundle via overrides when replay trips thresholds.",
            use="Let it work in bear; **Release defensive** (type RELEASE) restores saved knobs.",
            bull="Armed but inactive — normal.",
            neutral="Hold defensive if churning chop.",
            bear="DEFENSIVE ACTIVE — don't SKYNET-Apply aggressive offsets in parallel.",
            narrative="Circuit trips at 3am; you wake up to bear regime without touching SKYNET.",
            seealso="[Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro) · [Appendix S](#appendix-s--trust-phase-skynet-bias)",
        )
        + card(
            "Treasury (placeholder)",
            what="Future sideline Tangem tranche deploy — not wired.",
            use="Fund manually: Config → RLUSD issuer + Xaman send to bot address.",
            bull="—",
            neutral="—",
            bear="—",
            narrative="11k on Tangem stays manual until Phase 2 treasury ships.",
            seealso="[Funding changes](#funding-changes-scaling-toward-11k-xrp)",
        )
    )

    parts.append(
        """### SKYNET tab

SKYNET advisor — operator phase, market regime, Agent Smith, Full SKYNET, manual Ask.

"""
        + card(
            "Operator phase (trust / scale / aggressive)",
            what="Strategy bias for SKYNET suggestions — does not change knobs until Apply.",
            use="Match phase to tranche soak. Trust after deploy/SL streak; scale after clean realized week.",
            bull="Scale → Aggressive only with guardrails.",
            neutral="Trust or Scale.",
            bear="Trust — anti-bleed prompts; max_pending before offset↓.",
            narrative="You set Aggressive on day one — SKYNET suggests 0.08% offset; you Apply; SLs follow.",
            seealso="[Appendix S](#appendix-s--trust-phase-skynet-bias) · [Appendix T](#appendix-t--scale-phase-modest-accumulation) · [Appendix U](#appendix-u--aggressive-phase-bag-push)",
        )
        + card(
            "Market regime (bull / neutral / bear)",
            what="Tape bias for SKYNET Ask + Agent Smith — mirrors PRO/defensive posture language.",
            use="Set bear after SL-heavy night if circuit disabled. Apply suggestions manually.",
            bull="Bull — accumulate dips in prompts.",
            neutral="Neutral — anti-churn language.",
            bear="Bear — defensive; aligns with auto circuit bundle.",
            narrative="Regime bear + phase trust — SKYNET refuses to recommend offset below 0.15.",
            seealso="[Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro)",
        )
        + card(
            "Agent Smith (Phase 2)",
            what="Bounded auto-suggestions every 3–5 cycles within guardrails.",
            use="Review purple knob highlights on Live; Apply safe changes manually.",
            bull="Allow modest risk/pending bumps inside guardrails.",
            neutral="Default guardrails.",
            bear="Pause Agent Smith during defensive circuit.",
            narrative="Purple ◆ on max_pending — Agent Smith agrees you need cap before offset.",
            seealso="[Tuning SKYNET](#tuning-skynet-ask-agent-smith-full-mode)",
        )
        + card(
            "Full SKYNET (Phase 3) & Manual Ask",
            what="Autonomous apply (confirmed) vs conversational Ask → Apply.",
            use="Full mode requires `ENABLE_FULL_SKYNET`. Kill/pause always override.",
            bull="Still cap with guardrails — not a license for 5% risk.",
            neutral="Ask for stale bid ladder diagnosis.",
            bear="Do not enable Full during bleed — use PRO + trust phase.",
            narrative="You Ask 'why no fills?' — SKYNET returns pending_buy_stale block with target entry math.",
            seealso="[Tuning SKYNET](#tuning-skynet-ask-agent-smith-full-mode)",
        )
    )

    parts.append(
        """### Config tab

Credentials, network, Telegram/HUD auth, **Send / withdraw**, transfer log.

"""
        + card(
            "Bot account & network",
            what="Address, RLUSD issuer (read-only resolved), secret, testnet, RPC.",
            use="Copy **rlusd_issuer** when funding from Xaman/Tangem. Never commit secrets.",
            bull="—",
            neutral="Verify mainnet + trust line before tranche.",
            bear="—",
            narrative="You paste issuer into Xaman — RLUSD lands on bot with correct trust line.",
            seealso="[Funding changes](#funding-changes-scaling-toward-11k-xrp)",
        )
        + card(
            "Send / withdraw from bot",
            what="Signed XRPL payment to any `r…` address. Type SEND to confirm.",
            use="Pause/stop engine before large withdrawals. Logged to transfers.csv + tax CSV.",
            bull="—",
            neutral="Tranche profit skim — small test send first.",
            bear="—",
            narrative="You SEND 50 XRP to cold wallet after pausing — tax row logs OUT.",
            seealso="[`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md)",
        )
    )

    return "\n".join(parts)


def main() -> None:
    src = SRC.read_text(encoding="utf-8")

    # Foundations from original
    foundations = extract_section(src, "## What this bot actually does", "## Risk & Entry")
    lifecycle = extract_section(src, "## The order lifecycle", "## Your dashboard")
    dashboard_intro = extract_section(src, "### Data speed", "### Why we place bids")
    fills = extract_section(src, "### Why we place bids", "## Risk & Entry")

    # Part 2 sections
    tax = extract_section(src, "## Tax & transfer records", "## Funding changes")
    funding = extract_section(src, "## Funding changes", "## Real-talk scenarios")
    troubleshooting = extract_section(src, "## Troubleshooting cheat sheet", "## Knob coupling")
    coupling = extract_section(src, "## Knob coupling", "## Live box snapshot")
    live_box = extract_section(src, "## Live box snapshot", "## Scenarios & suggested presets")
    checklist = extract_section(src, "## 48-hour watch checklist", "### Scenario T")
    starter = extract_section(src, "## Suggested starter settings", "## Tuning SKYNET")
    skynet = extract_section(src, "## Tuning SKYNET", "## Emergency controls")
    emergency = extract_section(src, "## Emergency controls", "---\n\n*Grow the bag")

    # Scenarios
    scenario_pat = re.compile(r"^### (Scenario ([A-Z])) — (.+)$", re.M)
    matches = list(scenario_pat.finditer(src))
    appendix_blocks: list[str] = []
    for i, m in enumerate(matches):
        letter = m.group(2)
        title = m.group(3)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else src.find("## 48-hour watch checklist")
        if end < 0:
            end = src.find("## Suggested starter settings")
        block = src[start:end].strip()
        appendix_blocks.append(scenario_to_appendix(block, letter, title))

    # T/U after checklist if duplicated - skip if already in matches
    extra = extract_section(src, "### Scenario T —", "### Quick reference")
    if extra and not any("Appendix T" in b for b in appendix_blocks):
        appendix_blocks.append(scenario_to_appendix(extra, "T", "Scale phase (modest accumulation)"))

    # Real-talk → why no buys table
    why_no_buys = extract_section(src, "### “Why no buys?” — today’s classic", "## Troubleshooting cheat sheet")
    why_no_buys = why_no_buys.replace("Scenario ", "Appendix ").replace("#scenario-", "#appendix-")

    # Build appendix index
    index_rows = []
    for m in matches:
        letter = m.group(2)
        title = m.group(3)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        index_rows.append(
            f"| **{letter}** | [Appendix {letter} — {title}](#appendix-{letter.lower()}--{slug}) |"
        )

    header = """# xLedgerMate Alpha — Trader's Manual

**Organized by HUD tab and card.** Scenarios live in [Appendices](#appendices--scenario-playbook) at the end.

Written for operators who have watched too many green candles turn red.

For install, VPS, dry-run cutover, and credentials: [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) · [`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md).

---

## How to read this manual

1. **Part 0** — what the bot does, lifecycle, data speed (read once).
2. **Part 1** — walk the HUD left-to-right: each **tab**, each **card**, with **Bull / Neutral / Bear** stance.
3. **Part 2** — funding, coupling, troubleshooting, soak checklists, SKYNET tuning.
4. **Appendices** — lettered scenario recipes (A–W) when Decision reason matches a pattern.

**Nav order:** Live · TA · Brackets · Open offers · Reports · Activity · **PRO** · SKYNET · Config

---

## Table of contents

- [Part 0 — Foundations](#part-0--foundations)
- [Part 1 — HUD guide](#part-1--hud-guide-by-tab-then-card)
  - [Always visible](#always-visible--header--sidebar)
  - [Live tab](#live-tab)
  - [TA tab](#ta-tab)
  - [Brackets tab](#brackets-tab)
  - [Open Offers tab](#open-offers-tab)
  - [Reports tab](#reports-tab)
  - [Activity tab](#activity-tab)
  - [PRO tab](#pro-tab)
  - [SKYNET tab](#skynet-tab)
  - [Config tab](#config-tab)
- [Part 2 — Operator playbook](#part-2--operator-playbook)
- [Appendices — Scenario playbook](#appendices--scenario-playbook)

---

## Part 0 — Foundations

"""

    part0 = (
        foundations
        + "\n\n---\n\n"
        + lifecycle
        + "\n\n---\n\n"
        + "### Your dashboard — what to watch\n\n"
        + "| Where | What it tells you |\n|--------|-------------------|\n"
        + "| **Ticker / sidebar** | Mode, mid, portfolio, inventory %, drawdown, session & realized P&L |\n"
        + "| **Live → Decision** | Last action + reason (start here when confused) |\n"
        + "| **PRO** | Realized replay + defensive circuit |\n"
        + "| **SKYNET** | Advisor phase & regime |\n"
        + "| **Config** | Funding & withdraw |\n\n"
        + dashboard_intro
        + "\n\n"
        + fills
    )

    part2_intro = """## Part 2 — Operator playbook

Cross-tab topics: tax logs, scaling capital, knob coupling, troubleshooting, soak discipline, SKYNET, emergencies.

"""

    why_section = f"""### Why no buys? — Decision reason cheat sheet

{why_no_buys.split('**Check Decision reason**', 1)[-1] if '**Check Decision reason**' in why_no_buys else why_no_buys}

"""

    appendices = (
        "## Appendices — Scenario playbook\n\n"
        "Lettered recipes — not gospel. Change **one knob**, watch Decision **10–20 cycles**.\n\n"
        "### Appendix index\n\n"
        "| | Appendix | When to use |\n|---|----------|-------------|\n"
        + "\n".join(index_rows)
        + "\n\n---\n\n"
        + "\n\n---\n\n".join(appendix_blocks)
        + "\n\n---\n\n"
        + extract_section(src, "### Quick reference — your “closer to live price” checklist", "## Suggested starter settings")
    )

    # Fix links in part2 sections
    def fix_links(text: str) -> str:
        text = re.sub(r"\]\(#scenario-([a-z])--", r"](#appendix-\1--", text, flags=re.I)
        text = text.replace("Scenario ", "Appendix ")
        text = text.replace("scenarios A–W", "Appendices A–W")
        text = text.replace("scenarios A–V", "Appendices A–W")
        return text

    out = "\n\n".join(
        [
            header.strip(),
            part0.strip(),
            build_part1().strip(),
            part2_intro.strip(),
            fix_links(tax),
            fix_links(funding),
            why_section.strip(),
            fix_links(troubleshooting),
            fix_links(coupling),
            fix_links(live_box),
            fix_links(checklist),
            fix_links(starter),
            fix_links(skynet),
            fix_links(emergency),
            fix_links(appendices),
            "\n*Grow the bag. Respect the spread. Read the reason string.*\n",
        ]
    )

    # Global link fixes
    out = re.sub(r"\]\(#scenario-([a-z])--", r"](#appendix-\1--", out, flags=re.I)
    out = out.replace("## Risk & Entry — your main weapons", "## Risk & entry (moved to Part 1 — Live tab)")
    out = re.sub(r"\n{4,}", "\n\n\n", out)

    DST.write_text(out, encoding="utf-8")
    print(f"Wrote {DST} ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()
