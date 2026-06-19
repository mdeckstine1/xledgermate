# XLedgerMate — WS + Pure A-S Manual

*Production path (`Ashigaru`). Pure A-S + WS book feed + on-chain competitor intelligence + advisory Grok.*

**Status (as of 2026-06-18, VPS soak):** Production **`ws-engine`** + **HUD `:8765`** on Ashigaru branch. Pure A-S + WS BookFeed + G2/G4/G7 + competitor/peer intel. HUD tabs: **Live**, **Inventory**, **Intelligence**, **Metrics**, **Book**, **Reports**, **Credentials**, **Config**. RLUSD-stable **wealth sidebar** (session Δ, skim/spot/rebal). **Book** tab: depth chart + L1–L3 ladder (L2/L3 planned until ledger sync). **Metrics**: G3 §7 grades + **G6 activation** tier (`hold` when spread capture needs attention). Grok analyze live when configured. Sacred HTTP-poll long-run untouched (validation corpus). AI / Grok is **strictly advisory** — never overrides A-S reservation.

**Critical path:** [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) — task checklist. **Run commands:** `groks input/CURSOR_HANDOFF_ROADMAP.md`. Update checkboxes + FOR_AI milestones on progress.

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

- Open http://127.0.0.1:8765 (hard refresh after any HTML edit: **Ctrl+Shift+R**).
- **Live tab**: WS book + A-S reservation, optimal spread, gamma/kappa, `would_quote`, G2/G7 posture, quote ladder (L1–L3), session fills / skim, soak strip (toxic@30s, markout, G6 tier).
- **Inventory tab**: Bot address (copy + QR), live XRP/RLUSD balances, **Wallet Δ** (portfolio change since session start — includes deposits), target ratio.
- **Intelligence tab**: Competitor + peer lane scrape, pressure scores, Grok analyze, advisory signals. JSONL: `logs/intel_decisions.jsonl`.
- **Metrics tab**: Phase E §7 grades (spread capture primary; inventory steering). **G6 activation** card — tier (`warming_up` → `pilot` → `active` → `scale_ready`; **`hold`** when spread capture is attention with ≥8 fills; **`halted`** on kill). Red hold card lists attention triggers + gate FAIL. Capture summary + recent intel tail.
- **Book tab**: Depth chart (bids left / asks right of mid), split ladder, touch, **our L1–L3** from `quote_intents` (L2/L3 dashed = planned until multi-level ledger sync). Full CLOB depth after ws-engine exports `book_bids`/`book_asks`.
- **Reports tab**: Soak-safe read-only reports from `logs/` (G6 activation, soak dashboard, fill age, CLOB/AMM monitor, …).
- **Config tab**: Quoting parameters, Intelligence APIs (Grok key/model), Telegram.
- **Credentials tab**: Bot wallet secrets (VPS production).

**Wealth sidebar (all pages):** RLUSD-stable portfolio, session Δ, skim / spot / rebal decomposition, XRP @ mid, share %. Distinct from **Skim Δ** on soak strip (engine `session_spread_capture_xrp` — trading edge, not deposits).

**G6 activation (Metrics + soak strip):** Grades from CSV fills + runtime. Spread capture **attention** (e.g. high positive % but &lt;8 bps avg) → tier **`hold`**, gate **FAIL** — keep size conservative; review G2/G4 brakes. CLI: `python -m experimental.ws_feed.live_activation_grading --gate`.

The tester also writes `logs/ws_as_demo_runtime.json` (frequent + at end) so you can load the exact same data into the main Streamlit GUI for deeper side-by-side views (sidebar, tickers, full "Why these quotes?" etc.).

**Important:** After any edit to `hud/index.html` or the tester, **restart the tester process**. The HTML is read at server start; the Python state is in-memory.

---

## Competitor Intelligence & Grok/xAI API (Advisory Layer)

On-chain scraping (via the live book + connector) builds per-maker profiles (posted spreads/sizes, activity, sides, cancel proxies, domain if set). Aggregates (observed market spread, pressure score, active makers, depth) are fed as better inputs to pure A-S (effective vol/liquidity/pressure) so the math can be smarter about when to be aggressive.

**G2 spread-quality scaler (v2.1.0)**: `experimental/ws_feed/spread_quality_scaler.py` — brake-only dimmer on rolling fill toxicity / 30s markout. Applies `size_mult` (≤1.0, no win-chase) and `spread_mult` (vol widen) inside `PureQuotePath` before A-S ladder. **Never** touches reservation or `would_quote`; **not** coupled to kill switch. HUD Live tab shows G2 grade + multipliers. See [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) Phase G2.

**Formal pressure model (landed 2026-06-09)**: `experimental/competitor_pressure.py` — `CompetitorPressure` + `apply_competitor_pressure` (monotonic: low pressure → lower vol, higher size_mult, gamma_scale, observed-spread book anchor). Side-aware for XRP-heavy rebalance (ask_pressure when XRP heavy). Integrated in the PureQuotePath (`engine_adapter_example.compute_pure_as_decision`): accepts competitor_intel, applies before pure A-S call. Outputs `competitor_pressure`, `pressure_*` fields + rationale. Never touches reservation or the inside-book decision.

**AI advisory (integrated in PureQuotePath)**: `AIAdvisorySignal` in `ai_analysis/base.py`. Hooked inside `compute_pure_as_decision` (after pressure, as peer per review). Further advisory mults on vol/size (e.g. low pressure + AI "skim harder" → extra boost). Attached to decision output + note. Strictly advisory; real AIAnalyzer (stub/local/grok) can be passed. See Intelligence tab + tester for live signals. Use with sacred_economics for A/B validation of "skim harder" lift.

**Grok/xAI support (now live with real responses):**
- Configured in the **Config tab** (provider=grok, real xai-... key, model field + "Fetch available models for this key" button).
- The fetch button calls real `/list_models` (xAI `/v1/models` using current key) and renders a proper `<select>` dropdown. `grok-3` is always forced to the top as "(recommended)" and pre-selected. Changing the dropdown auto-applies.
- "Apply Changes" pushes live via `/set_intel_config` (no restart needed).
- Real calls happen in the HUD server's `/analyze_competitor` endpoint (POST with competitor `r...` address + optional live pressure/observed-spread/inventory context from the tab).
- Prompt is focused on XRPL MM patterns (spreads, sizes, refresh/cancel behavior, inventory signals) + how pure A-S can compete/skim harder given current competitor_pressure.
- Output: rich rationale surfaced in the Intelligence tab result box + can feed decision notes. **Never mutates A-S**.
- CLI equivalent: `--intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-3`
- The per-sample "AI rationale" / posture cards (in Live tab) still use the enhanced local stub (folds in competitor_pressure) to avoid rate limits. The dedicated "Analyze with AI" button + address input is for full real Grok on specific scraped makers.
- Many keys return a mix of chat + preview/experimental models (grok-4.20-*, grok-imagine-*, etc.). The UI now surfaces a clean recommended list with grok-3 at top; non-chat models should be avoided for text analysis.

**Optional future ideas:**
- Internal nicknames for competitors: a purely local (never on-chain or shared) map (e.g. small JSON file or in-memory) keyed by r-address, so the operator can assign memorable labels like "Bob the aggressive L1 sniper" or "Carol the rebalancer" for easier recall when looking at Top Scraped / analyses. The HUD could show "nickname (r...)" and support editing the map from the Config or Intelligence tab. No impact on A-S math or shared data.

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
- Grok tokens: rotation, budgets, prompt library, richer live context in prompts, wiring real AIAdvisorySignal more deeply (more details later). Real responses now proven with grok-3.
- Full end-to-end replay + live tester measurement against the latest 150-fill+ corpus.
- Polish on real Grok path (model filtering in dropdown, richer prompts with full A-S state, persistent analysis history, wiring AIAdvisorySignal output more visibly into Live tab cards).

See `IMPLEMENTATION_PLAN.md` (Tier 3 / WS + pure A-S section) and `experimental/ws_feed/WS_HANDOFF.md` for the detailed committed direction.

All of this lives in `experimental/` on the parallel branch. No changes to the sacred long-run testing ground.