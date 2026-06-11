# Pure A-S Critical Path

**Status:** Active — we are moving from **hard `market_edge_met` gates** to **WS + pure Avellaneda-Stoikov** as the production quoting model.  
**Branch:** `grok-ws-feed` (experimental) · **Sacred data / VPS Gate 2:** `grok-tier-2-collab` (labeled corpus only until swap sign-off)  
**Last updated:** 2026-06-10

This is the **single checklist** for WS + pure A-S work. Other docs point here; do not duplicate task lists elsewhere.

---

## Direction

| From (legacy) | To (committed) |
|---------------|----------------|
| HTTP BookOffers poll | WS `BookFeed` / `WsBookFeed` |
| Hard `market_edge_met` + heuristic vetoes | Pure A-S: reservation inside book + optimal spread |
| Low presence on thin books (~11%) | Higher safe presence when math allows (~90%+ on sacred replay) |
| Grok/pressure as ideas | Advisory inputs to A-S (vol, spread anchor, size) — **never** override reservation |

**Safety contract:** `would_quote` = reservation inside live best bid/ask. Pressure, Grok, and AI only tune **inputs**.

**Sacred long-run** (VPS gated engine) stays running for Gate 2 data until operator signs off on wholesale swap.

---

## Doc map (read order)

| # | File | Use |
|---|------|-----|
| 1 | **This file** | Critical path checklist |
| 2 | [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) | Run tester + HUD + Grok |
| 3 | [`../groks input/FOR_AI_AND_FUTURE_SESSIONS.md`](../groks%20input/FOR_AI_AND_FUTURE_SESSIONS.md) | VPS ops, milestones |
| 4 | [`../experimental/ws_feed/WS_HANDOFF.md`](../experimental/ws_feed/WS_HANDOFF.md) | Architecture + wiring parity |
| 5 | [`../groks input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md`](../groks%20input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | Gate pass metrics (doc 05) |
| 6 | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Tiers 1–2 history + field gates |
| 7 | [`../groks input/collab/THREAD.md`](../groks%20input/collab/THREAD.md) | Grok ↔ Cursor log |

**Session quick start:** [`../groks input/CURSOR_HANDOFF_ROADMAP.md`](../groks%20input/CURSOR_HANDOFF_ROADMAP.md) (run commands + file pack only).

---

## Run the lab (daily)

```powershell
cd C:\Users\micha\xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose `
  --intel-ai-provider grok --intel-ai-key xai-YOURKEY --intel-ai-model grok-3
```

Open http://127.0.0.1:8765 · Artifacts: `logs/ws_as_demo_runtime.json`

**Measure sacred corpus:**

```powershell
python experimental/grokster.py
python -m experimental.ws_feed.replay_long_run --as-mode pure --economics
```

---

## Critical path checklist

Update checkboxes when items ship. Mark **FOR_AI § Milestones** + **THREAD** on major completions.

### Phase 0 — Done (foundation)

- [x] WS probe validated (`experimental/ws_feed/PROBE_RESULTS.md`)
- [x] Pure A-S strategy (`strategy/avellaneda_strategy.py`)
- [x] Replay + grokster on sacred corpus (presence lift)
- [x] `sacred_economics.py` — capture, neg-fill %, balance-delta, marginal oracle
- [x] `competitor_pressure.py` + tests — monotonic vol/gamma/size/spread inputs
- [x] `engine_adapter_example.py` — PureQuotePath sketch (pressure + AI advisory hook)
- [x] Live tester + HUD (`:8765`) — Intelligence tab, competitor scrape
- [x] Real Grok on-demand (`grok-3`, model dropdown, `/analyze_competitor`)
- [x] Unlimited tester runs (`--seconds 0`)

### Phase A — Measurement (do before predator / scale claims)

- [ ] **A1** Sacred economics A/B: baseline vs pure vs pure+pressure vs pure+pressure+AI (`grokster` / `replay_long_run --economics` flags)
- [ ] **A2** Runtime analysis script over `logs/ws_as_demo_runtime.json` (pressure variance, spread vs optimal, would_quote flips, competitor correlation)
- [ ] **A3** Gamma/kappa calibration profile from grokster + live HUD samples → checked-in defaults or `experimental/ws_as_calibration.yaml`

### Phase B — Production-shaped pure path (experimental only)

- [ ] **B1** Unify `live_pure_as_tester` on `WSBookFeedAdapter.compute_pure_as_decision` (single PureQuotePath)
- [ ] **B2** Dynamic sizing helper (`L1 = min(config, k × XRP bal)`; ask boost when XRP-heavy + low ask-pressure)
- [ ] **B3** WS book age modulator (stale → higher effective vol; fresh + low pressure → allow aggression)
- [ ] **B4** Tight-book decision notes (explain 0 quotes: spread floor vs reservation outside book — operator clarity)

### Phase C — Exploitation layer (cash + Grok key)

- [ ] **C1** Competitor nicknames (local JSON map; HUD display/edit)
- [ ] **C2** Grok exploitation output → optional `AIAdvisorySignal` (rate-limited; not every cycle)
- [ ] **C3** Prompt iteration from real analyses (especially one-sided bidder + defensive refresh patterns)
- [ ] **C4** Track "presence when pressure low vs high" + "Grok suggestion → outcome" in runtime export

### Phase D — Infrastructure (pre-swap)

- [ ] **D1** `WsBookFeed` hardening (reconnect backoff, `is_fresh` / max age guards, 30+ min soak)
- [ ] **D2** Promotion step: dry-run offers on WS path (same PureQuotePath, no sacred engine edits)
- [ ] **D3** Streamlit side-by-side demo (`ws_as_demo_runtime.json` vs sacred runtime)
- [ ] **D4** Swap readiness report from `replay_long_run` (wiring parity + economics summary)

### Phase E — Deferred (explicitly not now)

- [ ] **E1** Wholesale VPS replace with WS + pure A-S (post Gate 2 + operator opt-in)
- [ ] **E2** Merge `grok-ws-feed` → `grok-tier-2-collab` mid–Gate 2
- [ ] **E3** 11k-only funding / predator P&L targets (hypothesis until A1–A3 + live fills validate)
- [ ] **E4** Touch `engine/trading_engine.py` on collab branch for WS deploy

---

## Promotion ladder (hard gate → pure A-S)

1. Sacred replay economics (Phase A)  
2. HUD observe-only + long runs (running now)  
3. Dry-run offers on WS path (D2)  
4. Shadow: WS pure vs HTTP gated on same wallet (optional)  
5. Wholesale server swap (E1)

---

## Key files

```
experimental/ws_feed/live_pure_as_tester.py   # live loop
experimental/ws_feed/engine_adapter_example.py # PureQuotePath
experimental/competitor_pressure.py
experimental/sacred_economics.py
experimental/grokster.py
experimental/ws_feed/replay_long_run.py
experimental/ai_analysis/grok_analyzer.py
strategy/avellaneda_strategy.py
```

---

## Weekly scoreboard (pure path)

Use [`groks input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md`](../groks%20input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) for Gate 2 VPS. For **experimental pure path**, track:

- Marginal capture oracle delta (A/B)
- Neg-fill % on attributed fills
- `would_quote` % on live HUD samples
- Spread vs `as_optimal_spread_pct` (why 0 quotes)
- Realized fills from funded account (when quoting)

**Do not** use presence alone as success.

---

## Maintenance

When a checkbox ships: update this file, FOR_AI milestone, THREAD (`— Cursor`), and progress row in IMPLEMENTATION_PLAN Tier 3.
