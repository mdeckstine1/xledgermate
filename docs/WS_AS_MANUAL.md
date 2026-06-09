# XLedgerMate — WS + Pure A-S Manual

*Experimental / committed future path (grok-ws-feed branch). Pure A-S + WS book feed + on-chain competitor intelligence + advisory Grok/xAI analysis.*

**Status (as of this writing):** Functional in `experimental/ws_feed/`. Sacred long-run (HTTP poll + hard gate on VPS) is untouched and remains the data generator. All work here is for post-Gate 2 wholesale server replace. AI / Grok is **strictly advisory** — never touches A-S reservation price or quoting decisions.

---

## The Core Idea (WS + Pure A-S)

Instead of the current hard `market_edge_met` gate + many heuristic vetoes ("L1 too tight", "edge thin", toxicity off-book, momentum pauses, etc.), the production path will be:

- **WS BookFeed** (fresher incremental updates, per-side snapshots, low age, reconciliation) as the primary book source.
- **Replicated long-run wiring** (exact `assess_inventory`, `build_quote_adjustments`, dynamic policy, toxicity, momentum, inventory steering, etc.) for rich decision provenance and log/GUI continuity.
- **Pure Avellaneda-Stoikov (A-S)** as the quoting engine:
  - Reservation price (gamma × inventory risk) must be **inside** the live best bid/ask.
  - Optimal spread (kappa + vol) sets competitive levels.
  - Built-in math protections only. No extra binary gates.

**Result (from replays on the exact sacred hard-gate corpus):** ~90–94% presence vs ~11% baseline, 93%+ flip rate on the historical "Generated 0 quotes / hard gate" cases, 0% modeled high-tox risk among the extra quotes. Full wiring strings are preserved so the operator still sees the familiar "inventory slight_xrp_heavy → steer quotes; operating mode: market make; ..." context.

The long-run hard-gate engine stays sacred (data source only). When Gate 2 signs off, the remote server code is replaced wholesale with this package.

---

## Running the Live Observation Surface (Tester + HUD)

The dedicated real-time HUD + tester is the place to watch pure A-S + WS + competitor intel in action.

```powershell
cd xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 600 --verbose --profile tight_spread
```

- Open http://127.0.0.1:8765 (hard refresh after any HTML edit).
- **Live tab**: WS book + A-S reservation (with bid/ask margins), optimal spread, gamma/kappa, would_quote (pure math), suggested levels, rich decision note (wiring strings + "PURE A-S (built-in protection)"), recent decisions.
- **Config tab**: Bot wallet balances, L1-L3 commitments (tied to bot), quoting parameters (profile selector + explanatory text moved here from old sidebar), **new Intelligence APIs card** (provider, key, model, enabled — for Grok/xAI competitor address trending).
- **Inventory tab**: Bot address (copy + real QR via server), live XRP/RLUSD balances (demo deposit/withdraw buttons that update displayed inventory for testing), L1-L3, target ratio.
- **Intelligence tab** (new): On-chain competitor scraping (active makers, observed market spread, pressure score (0=defensive → opportunity to scrape harder), total depth, top profiles with spreads/activity/sides + domain if set on-ledger). Aggregates feed A-S inputs (pressure as vol/liquidity proxy). "Skim harder" playbook. AI competitor address analyzer (demo button; real Grok when configured).
- **Credentials tab**: Demo secrets (never real in this surface).

The tester also writes `logs/ws_as_demo_runtime.json` (frequent + at end) so you can load the exact same data into the main Streamlit GUI for deeper side-by-side views (sidebar, tickers, full "Why these quotes?" etc.).

**Important:** After any edit to `hud/index.html` or the tester, **restart the tester process**. The HTML is read at server start; the Python state is in-memory.

---

## Competitor Intelligence & Grok/xAI API (Advisory Layer)

On-chain scraping (via the live book + connector) builds per-maker profiles (posted spreads/sizes, activity, sides, cancel proxies, domain if set). Aggregates (observed market spread, pressure score, active makers, depth) are fed as better inputs to pure A-S (effective vol/liquidity/pressure) so the math can be smarter about when to be aggressive.

**Formal pressure model (landed 2026-06-09)**: `experimental/competitor_pressure.py` — `CompetitorPressure` + `apply_competitor_pressure` (monotonic: low pressure → lower vol, higher size_mult, gamma_scale, observed-spread book anchor). Side-aware for XRP-heavy rebalance (ask_pressure when XRP heavy). Integrated in the PureQuotePath (`engine_adapter_example.compute_pure_as_decision`): accepts competitor_intel, applies before pure A-S call. Outputs `competitor_pressure`, `pressure_*` fields + rationale. Never touches reservation or the inside-book decision.

**AI advisory (integrated in PureQuotePath)**: `AIAdvisorySignal` in `ai_analysis/base.py`. Hooked inside `compute_pure_as_decision` (after pressure, as peer per review). Further advisory mults on vol/size (e.g. low pressure + AI "skim harder" → extra boost). Attached to decision output + note. Strictly advisory; real AIAnalyzer (stub/local/grok) can be passed. See Intelligence tab + tester for live signals. Use with sacred_economics for A/B validation of "skim harder" lift.

**Grok/xAI support (now live):**
- Configured in the **Config tab** (provider=grok, real xai-... key, model=grok-beta, enabled).
- "Apply" pushes live via `/set_intel_config` (no restart needed for the current session).
- Real calls happen in the HUD server's `/analyze_competitor` endpoint (POST with a competitor `r...` address).
- Prompt is focused on XRPL MM patterns + how pure A-S can compete/skim harder.
- Output: rich rationale for the Intelligence tab + decision notes. **Never mutates A-S**.
- CLI equivalent: `--intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-beta` (pre-fills state + form).
- The per-sample "AI rationale" (in notes) still uses the enhanced local stub (which already folds in competitor pressure) to avoid rate limits. The dedicated address button is the place for real Grok on specific trending ledger addresses.
- Llama3/stub is deprecated for the competitor intel use-case.

**How it helps skim harder (without touching A-S core):**
- Low competitor pressure (wide/defensive observed spreads) → lower effective vol into A-S → reservation closer to mid → more presence / tighter quotes exactly where competitors are weak.
- High pressure → A-S math naturally backs off (protection via reservation inside book).
- You see the "why" (profiles + Grok summary) in one tab while the bot continues to decide via pure math.

More token details, rotation hygiene, cost tracking, richer prompts (full profiles + history), and distillation targets will come later.

---

## How This Fits the Overall Strategy

(See `STRATEGY_MANUAL.md` for the plain-English "what the bot is trying to do with your money.")

Pure A-S + WS is the path to **competitive field MM** (high time on touch + positive realized spread bps + low toxic) while keeping the safety the long-run already proved. The Intelligence layer (scrape + Grok) is the operator's "extra pair of eyes" for deciding when to be hungrier — without ever adding hard rules on top of the A-S math.

The sacred long-run (hard gate) stays untouched and continues generating the exact labeled "blocked but maybe skimmable" cases we need for calibration and measurement.

---

## Next (High-Level)

- Production gamma/κ from current sacred data + live pure A-S runs.
- Quote level realism on today's tight books.
- Engine adapter + BookFeed protocol (still experimental only).
- 30+ min probes exercising the hardened feed.
- Post-Gate 2: swap procedure, operator opt-in, wholesale replace.
- Grok tokens: rotation, budgets, prompt library, batch labeling for distillation (more details later).
- Full end-to-end replay + live tester measurement against the latest 150-fill+ corpus.

See `IMPLEMENTATION_PLAN.md` (Tier 3 / WS + pure A-S section) and `experimental/ws_feed/WS_HANDOFF.md` for the detailed committed direction.

All of this lives in `experimental/` on the parallel branch. No changes to the sacred long-run testing ground.