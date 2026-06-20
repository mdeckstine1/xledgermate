# Changelog

All notable changes to XLedgerMate are documented here.  
Version numbers follow [Semantic Versioning](https://semver.org/) where practical.

---

---

## [2.1.29] — 2026-06-20 (`Ashigaru Kaizen II`)

**Theme:** A2.1 solo fill-rate tune — empty-book quotes closer to touch, less A3 churn.

### Changed

- **G7 v1.4** — solo empty lane: two-sided **join** (5 bps) on balanced/slight_*; only full `xrp_heavy` stays passive both. Fixes `slight_xrp_heavy` misclassified as full xrp_heavy.
- **A3 solo** — max ages 120s ask / 150s bid when `peer_lane_empty` (vs 60/90).
- **Sync** — solo mode disables `preserve_touch_queue` for faster quote refresh.

---

## [2.1.28] — 2026-06-20 (`Ashigaru Kaizen II`)

**Theme:** Acquisition metrics — session edge-positive inventory vs spot (A2 soak instrumentation).

### Added

- **`acquisition_metrics.py`** — `xrp_per_rlusd_spent`, `buy_cost_vs_mid_bps`, `solo_acquire_fire_rate`, capture by inventory state, spot vs skim ratio.
- **Engine** — M6 fill context (`solo_acquire`, inventory), intel cycle `peer_lane_empty` / `worst_vs_touch_bps`, `acquisition_metrics` on `runtime_state.json`.
- **`scripts/acquisition_metrics_report.py`** — offline session report; HUD Reports tab entry.

---

## [2.1.27] — 2026-06-20 (`Ashigaru Kaizen II`)

**Theme:** A2+A3 live deploy — solo acquisition + stale-quote guard; A1 segment closed.

### Deployed (VPS)

- **A2** — G7 v1.3 solo lane posture + G4 `solo_acquire` (empty peer band, low toxic).
- **A3** — `stale_quote_guard.py` auto-cancel (ask 60s / bid 90s / mid-move stale).
- **HUD** — marquee readability, favicon, boot hardening, `_check_hud_js.py` pre-deploy check.

### A1 segment

Closed **Fail**: 78 fills — SELL **−0.197** XRP vs BUY +0.096; session bps 0.43. Fresh A2+A3 soak ~50 fills vs baseline.

---

## [2.1.25] — 2026-06-20 (`Ashigaru Kaizen II`)

**Theme:** A3 stale-quote tail — auto-cancel aged quotes before toxic SELL fills (built; deploy after A2).

### Added

- **`stale_quote_guard.py`** — ask max age 60s (45s when toxic@30s ≥ 25%), bid 90s, mid-move stale cancel (≥8 bps + age >30s).
- **Engine** — `_sync_offers` merges stale cancels even when `preserve_touch_queue=True`; `A3 stale-quote:` decision log lines.

### Note

VPS remains on **v2.1.23** (A1 segment soak). Deploy **v2.1.25** bundled with A1/A2 after ~50-fill A1 analysis.

---

## [2.1.24] — 2026-06-20 (`Ashigaru Kaizen II`)

**Theme:** A2 solo acquisition — presence/fill rate on empty peer lane (built; deploy after A1 soak).

### Added

- **G7 v1.3** — `apply_solo_lane_posture`: balanced solo → bid join / ask passive; xrp_heavy solo → passive both; skips on G2 brake or toxic@30s ≥ 20%.
- **G4 v1.1** — `solo_acquire` grade: empty lane bid +6% / ask +2% when low toxic and G2 not defensive.
- **Runtime** — `g7_solo_acquisition` on `PureQuoteDecision` + HUD G7 synth.

### Note

VPS remains on **v2.1.23** (A1 segment soak). Deploy **v2.1.24** at segment end after ~50-fill A1 analysis.

---

---

## [2.1.17] — 2026-06-17 (`Ashigaru Kaizen II`)

**Theme:** G2/G7 operator labels on runtime and HUD.

### Added

- **Scaler labels** — `g2_scaler_label`, `g7_scaler_label`, `execution_brakes_summary` on `PureQuoteDecision` / `RuntimeState`.
- **G7 roles** — `bid_role` / `ask_role` (`join` / `passive` / `wide`) in `execution_envelope.py`.
- **HUD** — Session fills card shows G2 scaler, G7 queue, and queue-vs-touch rows.

---

## [2.1.16] — 2026-06-18 (`Ashigaru Kaizen II`)

**Theme:** G7 execution envelope — per-side touch backoff × G2 brake.

### Added

- **`execution_envelope.py`** — inventory-asymmetric touch (join side 3 bps, passive 8 bps) × `g2.spread_mult`.
- **Visibility** — `quote_visibility` + `worst_vs_touch_bps` on production runtime export.
- **RuntimeState** — `g7_summary`, `bid_touch_backoff_bps`, `ask_touch_backoff_bps`.

---

## [2.1.15] — 2026-06-18 (`Ashigaru Kaizen II`)

**Theme:** Engine-window bundle M2–M5 — fill age, stale-cross, production soak samples.

### Added

- **M2** — `OfferAgeTracker` in ws-engine (`_sync_offers` + `_detect_fills`); `effective_quote_age_at_fill_seconds` on runtime/HUD.
- **M3** — `reservation_crossed_after_ws_sample` when BBO moves during competitor-intel scrape.
- **M4** — `append_runtime_sample` each cycle; `sample_history`, C1 presence, zero-quote breakdown, soak gate on `runtime_state.json`.
- **RuntimeState** — `sample_history`, fill age, stale-cross, inside-L1 / res→BBO fields.

### Confirmed

- **M5** — `enforce_reservation_gate` already on `PureQuotePath` production path.

---

## [2.1.14] — 2026-06-16 (`Ashigaru Kaizen`)

**Theme:** WS feature switches in config — turn Telegram, intel, G2/G4, HUD Grok on/off.

### Added

- **`ws_*` / `telegram_*` feature flags** in `config.yaml` — `WsFeatureFlags` wired through ws-engine, HUD, hourly report.
- **`tests/test_ws_feature_flags.py`**

---

## [2.1.13] — 2026-06-16 (`Ashigaru Kaizen`)

**Theme:** Lean ws soak — single competitor scrape, HUD mirror only, VPS profile script.

### Changed

- **HUD** — reads `competitor_intel` from `runtime_state.json`; no duplicate on-chain scrape or intel JSONL append.
- **ws-engine** — persists competitor scrape blob for HUD.
- **HUD metrics** — G3/G6 grade rebuild throttled to 30s (was every 1s CSV walk).
- **`scripts/vps_lean_mm.sh`** — stop/disable Streamlit `:8501`/`:8502`; keep ws-engine + ws-hud only.

---

## [2.1.12] — 2026-06-16 (`Ashigaru Kaizen`)

**Theme:** Stop legacy session-balance kill on ws-engine soak; quieter Telegram when healthy.

### Fixed

- **ws-engine session balance kill** — removed sacred Gate 1 `session_balance_loss_kill_*` trip on WS path (was halting soak at −0.85 XRP); G6 / drawdown remain.
- **Hourly Telegram** — no standing “Clear kill” footer; resume hint only when kill file is active; no near-kill band warning on WS reports.

---

## [2.1.11] — 2026-06-15 (`Ashigaru Kaizen`)

**Theme:** Public HUD login + session-only fill display (E1.5 gate UI retired).

### Added

- **HUD authentication** — username/password session cookie; optional WebAuthn passkeys (`hud_auth.py`, `hud_bind_host`, `.env` / config credentials).
- **Phase H** — on-ledger arbitrage & multi-pair checklist in `PURE_AS_CRITICAL_PATH.md`.

### Changed

- **HUD / Streamlit fills** — show session count only (no E1.5 `/50` checkpoint).

### Tests

- **`tests/test_hud_auth.py`** — login, session cookie, 401 redirect.

---

## [2.1.10] — 2026-06-15 (`Ashigaru Kaizen`)

**Theme:** Hourly Telegram for WS soak + trustworthy WS fill capture for G6.

### Added

- **Hourly Telegram (WS)** — fill counts (1h / session / WS total), G6 tier, presence %, optional HUD link via `telegram_hud_url`.
- **HUD mobile layout** — viewport + narrow-screen CSS so `:8765` works on phone/tablet.
- **WS-engine start MAJOR** — session boundary for hourly/session fill stats.

### Changed

- **Branch rename** — production VPS branch `Ashigaru` → **`Ashigaru-Kaizen`** (continuous improvement line).

### Fixed

- **WS fill `profit_xrp_equiv`** — uses mid at last quote sync (`_last_sync_mid`), not stale cycle mid; unlocks G6 spread-capture grades.

---

## [2.1.9] — 2026-06-15 (`Ashigaru`)

**Theme:** Fix ws-engine runtime persist after G4 — HUD and intel log live again.

### Fixed

- **`RuntimeState` G4 fields** — `g4_size_mult`, `g4_grade`, `g4_active`, `g4_summary` (fixes `TypeError` blocking `runtime_state.json` saves since 2.1.8).
- **`RuntimeStateStore.load()`** — restores `as_mode`, reservation, and WS book fields on restart.

---

## [2.1.8] — 2026-06-15 (`Ashigaru`)

**Theme:** G6 live activation grading — §7 portfolio + capture + structural signals on Metrics tab.

### Added

- **G6 live activation grading** — `experimental/ws_feed/live_activation_grading.py`; tiers (`warming_up` → `pilot` → `active` → `scale_ready`); CLI `--gate`; report `logs/g6_activation_report.json`.
- **HUD G6 pill** — Metrics tab shows activation tier + summary from `performance_metrics.activation`.
- **`--g6-activation`** on `replay_long_run.py`.

### Changed

- **`VERSION` / `WS_AS_VERSION` → 2.1.8** — G6 checked off in `PURE_AS_CRITICAL_PATH.md`.

---

## [2.1.0] — 2026-06-15 (`Ashigaru`)

**Theme:** Phase E complete (live ws-engine E1.5 PASS) + **G2 spread-quality scaler** on production path.

### Added

- **G2 spread-quality scaler** — `experimental/ws_feed/spread_quality_scaler.py`; brake-only `size_mult` / `spread_mult` from rolling toxicity + 30s markout; no win-chase, no kill coupling.
- **HUD inventory tab** — on-ledger bot balances, funding plan vs `risk_capital_xrp`, XRP share bar (Xaman stays separate until operator funds).
- **HUD E1.5 fill count** — authoritative CSV count for gate display (`ws_fills_csv`).

### Changed

- **`VERSION` / `WS_AS_VERSION` → 2.1.0** — G2 wired in `PureQuotePath`, `ws_pure_engine`, HUD Live tab.
- **`fill_quality.assess()`** — multipliers delegated to G2 module (single policy source).
- **Phase E** marked complete in `PURE_AS_CRITICAL_PATH.md`; E3 funding blocked until dev complete.

---

## [2.0.0] — 2026-05-29 (`Ashigaru`)

**Theme:** WS + pure A-S lab reaches **v2** — soak gates, dry-run offers, peer-lane intel, swap-readiness on the path to live MM.

### Added

- **G1 peer-lane intel** — posted-touch band (0.4×–2.5× our L1), fled-touch proxy, peer-only pressure (`peer_lane.py`, `competitor_intel.py`).
- **Pure dry-run executor** — virtual offers on WS path without sacred engine edits (`pure_dry_run_executor.py`).
- **Swap readiness report** — wiring parity + economics gate (`swap_readiness_report.py`).
- **WS feed hardening** — reconnect backoff, `is_fresh`, book-age modulator, zero-quote operator notes.
- **Dynamic L1 sizing** — `min(config, k × balance)` with inventory/pressure skew.
- **Streamlit WS compare** tab + expanded runtime analysis / C2 soak gate.

### Changed

- **`WS_AS_VERSION` → 2.0.0** — single source in `experimental/ws_feed/WS_AS_VERSION`; `PureQuotePath` reads it at import.
- **Project `VERSION` → 2.0.0** — Ashigaru product line (sacred VPS Gate 2 engine unchanged until Phase E swap).

### Docs

- [`docs/PURE_AS_CRITICAL_PATH.md`](docs/PURE_AS_CRITICAL_PATH.md) — Phases A–D complete; Phase G G1 shipped.
- [`experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md) — operator doctrine for peer lane.

---

## [1.4.4] — 2026-05-29 (`tier-2-polish`)

**Theme:** Gate 1 runs survive bad book ticks without spread-fail kill; **Tier 1 + Gate 1 signed off** — Gate 2 current.

### Fixed

- **Spread-fail kill on bad book feed** — Missing, incomplete, or **inverted** book no longer increments the consecutive spread-failure streak or trips kill (`book_unreliable` on `QuoteValidationResult`). Live orders still pause until the book is sane.

### Docs

- **Tier 1 + Gate 1 complete (operator sign-off)** — plumbing stable on mainnet; formal metric checklist partially met; shortcomings documented; **Gate 2 `tight_spread` current** ([`IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md), [`MAINNET_PILOT.md`](docs/MAINNET_PILOT.md), [`AUDIT_REPORT.md`](docs/AUDIT_REPORT.md)).
- Operator health / session insights messaging updated for Gate 2 pilot.

---

## [1.4.3] — 2026-06-04 (`tier-2-polish`)

**Theme:** Crossed-book portfolio truth; Gate 1 safety before competitive pilot.

**Docs (2026-06-05):** [`IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md), [`STRATEGY_MANUAL.md`](docs/STRATEGY_MANUAL.md), [`OPERATOR_MANUAL.md`](docs/OPERATOR_MANUAL.md), [`MAINNET_PILOT.md`](docs/MAINNET_PILOT.md), [`README.md`](README.md) — Gate 1 criteria (balance PnL), v1.4.3 kills, Tier 2.5 backlog.

### Fixed

- **Crossed / inverted order book** — `compute_mid_price` returns `None` when bid ≫ ask (no longer uses stale ask as mid). Rejects RLUSD/XRP &lt; 0.45. Portfolio, session PnL, and GUI use **last valid mid** when the book is bad (`connectors/xrpl_connector.py`, `engine/trading_engine.py`).
- **False spread-capture on fills** — Fill logging uses trustworthy mids only (avoids −12 XRP phantom lines on bad books).
- **Session baseline** — Set only after a trustworthy mid (not on first crossed-book tick).

### Added

- **Session balance loss kill** — Optional halt when balance PnL &lt; **−0.35 XRP** after **≥25 fills** (`session_balance_loss_kill_xrp`, `session_balance_loss_kill_min_fills`; `0` = off). Configurable in **Advanced → Kill settings**.
- **`scripts/portfolio_bleed_analysis.py`** — Balance drift across mainnet runs.
- **Tests** — `tests/test_book_mid_integrity.py`, `tests/test_trustworthy_mid.py`.

---

## [1.4.2] — 2026-06-04 (`tier-2-polish`)

**Theme:** Drawdown kill safety on stale order books; toxicity gates need enough fills.

### Fixed

- **Toxicity gates on small samples** — `safe` requires **8 fills** before off-book / pause-side / refresh-pause use toxic ratio (fixes 50% on 4 fills emptying the book). Early window uses softer fill-quality sizing only.
- **Toxicity hysteresis** — off-book enters at 20% adverse, exits below **15%** (avoids flicker at 22–25%).
- **Risk capital sync** — GUI warns when config capital ≠ live portfolio; one-click sync (`utils/risk_capital_sync.py`).
- **Weekly skim report** — `scripts/weekly_skim_report.py` with Gate 1/2 checklist and capture bps.

- **Daily drawdown kill** — Invalid or missing mid (crossed/stale book, `ask=0`) no longer marks portfolio as XRP-only and trips a false ~40% drawdown kill. Drawdown state is unchanged for that cycle; kill is evaluated only after a valid RLUSD/XRP mid mark (`risk/drawdown.py`, `engine/trading_engine.py`).

### Added

- **`is_valid_portfolio_mid`** and tests for invalid-mid drawdown guard (`tests/test_drawdown.py`).

---

## [1.4.1] — 2026-06-03 (`tier-2-polish`)

**Theme:** Unified dynamic quoting, audit cleanup, visibility on thin books.

### Added

- **Dynamic quoting policy** (`core/dynamic_quoting_policy.py`) — single resolver for at-touch / near-touch / spread-mid / off-book posture from profile bounds + market health + toxicity.
- **Shared caps** (`core/quote_caps.py`, `core/toxicity.py`) — one touch-distance cap and adverse-ratio helper across order manager, validation, and refresh.
- **Marquee ticker** (`gui/ticker.py`) — policy line and decision feed above the command bar.
- **Profile toxicity fields** — `toxic_no_touch_ratio`, `toxic_pause_side_ratio` per built-in profile.
- **Docs** — [`docs/AUDIT_REPORT.md`](docs/AUDIT_REPORT.md) (conflicts found and fixed).

### Changed

- **Quote decisions** — removed legacy `resolve_quoting_posture`; self-bailout runs after policy; earlier pause on XRP-heavy + falling tape.
- **Book pressure** — profile sensitivity only (GUI preset sets config scale 1.0 to avoid double-multiply).
- **Poll refresh** — off-touch threshold uses policy visibility cap, not hardcoded 8 bps.
- **`RuntimeStateStore.load()`** — restores Tier-2 metrics (toxic ratios, refresh cadence, quoting policy label).
- **GUI** — one inventory pause slider; market suggestion uses engine profile when running.

### Removed

- **`resolve_quoting_posture`** / `QuotingPosture` (superseded by dynamic policy).
- **`competitive_near_touch_max_backoff_pct`** config key (unused; backoff in profile bounds).

---

## [1.4.0] — 2026-05-30 (`tier-2-fix`)

**Theme:** Tier 2 execution + truth — profile-owned queue cadence, ledger fills, multi-horizon markout.

### Added

- **Profile execution layer** (`core/profile_execution.py`) — each profile owns order-keep tolerances, poll interval, full refresh cadence, toxic pause threshold, and markout sensitivity.
- **Tiered refresh loop** — fast book poll (profile-owned, e.g. 15–20s) vs full quote refresh (30–90s); mid-move promotes to full refresh.
- **Ledger-accurate fills** — `account_tx` scan via `monitoring/ledger_fills.py`; tx hash on CSV rows when available.
- **Multi-horizon markout** — +30s and +5m toxic classification feeding `FillQualityTracker` and GUI.
- **RPC failure kill switch** — consecutive cycle failures trip kill (`rpc_failure_kill_streak`).
- **Execution metrics** — cancel/fill ratio, session cancels/keeps, toxic ratio on Dashboard.
- **Tests** — `test_profile_execution`, `test_ledger_fills`, `test_fill_quality_markout`.

### Changed

- **Order sync tolerances** now resolve from **active profile** (config can only tighten, not loosen).
- **Toxic refresh pause** — skips order refresh when toxic ratio exceeds profile threshold.
- **Auto profile switch log** includes vol/liquidity/book spread snapshot.
- **Command bar persistence** — live fragment re-injects theme CSS so header pills/layout survive 5s refresh.

---

## [1.3.9] — 2026-05-30 (`good-to-great`)

**Theme:** Good → great MM — edge capture, queue preservation, harder protection.

### Added

- **Edge guard widens spread** (not size-only) when min/market edge thin; favorable `capture_edge_pct` tightens/widens aggression.
- **Selective order refresh** — keep matching open offers; cancel/replace only when price/size drift (`engine/order_sync.py`).
- **Inventory circuit breakers** — pause bids/asks when XRP share exceeds target ± `inventory_max_deviation`.
- **Multi-trigger kill switch** — consecutive spread-check failures; toxic fill ratio threshold.
- **Per-fill spread capture** — `profit_xrp_equiv` in trade CSV via `monitoring/fill_economics.py`.
- **Auto-switch guard** — aggressive profile switches need +2 confirm cycles.
- **Tests** — `test_great_mm`, `test_kill_switch`, `test_drawdown`, `test_order_sync`.

### Changed

- **`dynamic_min_edge_enabled`** default **true** in `BotConfig` and example config.
- **Example L2 size** — `[50, 15, 0]` for depth skim.
- **`requirements.txt`** — added `pandas`, `pytest`.

### Removed

- **`auto_rollover_enabled`** — unimplemented config stub.

---

## [1.3.8] — 2026-05-30 (`debug/repair-set`)

**Theme:** Debug repair set — GUI save/apply reliability, profile presets, profit_mode guardrails.

### Fixed

- **Save Config** — White-screen / widget desync from stale session handles, double reruns, and Run One Cycle overwriting disk config.
- **Apply profile** — Now writes spread, edge, and book-pressure presets to disk (not only `active_profile`).
- **ImportError** — `normalize_profile_recommendation` moved to `utils/profile_recommendation.py` (avoids stale `core/` bytecode on Streamlit reload).
- **Suggested profile** — GUI always recomputes market assessment; no stale `profit_mode` from old `runtime_state.json`.

### Added

- **`utils/gui_profile_presets.py`** — Source of truth for Apply-profile control values per built-in profile.
- **`utils/profile_recommendation.py`** — Normalizes legacy `profit_mode` suggestions to `tight_spread`; defines auto-switch allowlist.
- **`utils/gui_runtime_sync.py`**, **`utils/manual_rebalance.py`** — GUI/runtime helpers.
- **Risk capital denomination** — `risk_capital_unit` / `risk_capital_rlusd` in settings and example config.
- **Tests** — `test_profile_gui_presets.py`; extended market conditions tests.

### Changed

- **Profit mode** — Never suggested or auto-switched; operators select manually on Controls when conditions are ideal.
- **`docs/STRATEGY_MANUAL.md`** — Rewritten in plain language with scenarios and narratives (v1.3.8).
- **`docs/OPERATOR_MANUAL.md`** — Suggested-profile wording aligned with manual-only profit mode.
- **Auto-switch idle default** — `auto_profile_inactivity_minutes` 120 → 30 in example config.

---

## [1.3.7] — 2026-05-29 (`mainnet-live`)

**Theme:** Live profile control — apply on the fly, full auto-switch with anti-flap guards.

### Added

- **Apply profile now** — Controls tab + suggested-profile Apply; no engine restart (`trust-no-ripple`-style queue via `logs/profile_request.json`).
- **Full auto profile switching** — All built-in profiles (including `profit_mode` and `tight_spread`), not defensive-only.
- **Auto-switch debounce** — `auto_profile_confirm_cycles` (default 3) and `auto_profile_switch_cooldown_minutes` (default 45).
- **Market hysteresis** — Sticky favorable/neutral and high-liquidity tiers to reduce recommendation jitter.
- **GUI** — Config vs engine profile banner; auto-switch idle/pending/cooldown status; cycle-aware stale-state threshold.
- **Tests** — `test_profile_request.py`, `test_auto_profile_state.py`; extended market conditions tests.

### Changed

- **Auto profile switching** — Requires repeated same recommendation + cooldown before switching (stops rapid safe ↔ profit flapping).

---

## [1.3.6] — 2026-05-29 (`mainnet-live`)

**Theme:** RLUSD trust line No Ripple — disable rippling for bot wallets.

### Added

- **`trust-no-ripple` CLI** — Sets `tfSetNoRipple` on the existing RLUSD trust line.
- **GUI** — Bot Account → **Disable RLUSD rippling**.
- **Preflight** — Warns when rippling is still enabled; confirms when No Ripple is set.
- **Tests** — `tests/test_preflight.py`.

### Changed

- **Setup RLUSD trust line** — New trust lines are created with No Ripple enabled.

---

## [1.3.5] — 2026-05-29 (`mainnet-live`)

**Theme:** `profit_mode` profile for calm, liquid markets.

### Added

- **`profit_mode` profile** — Tighter spreads, larger size, lower min edge than `tight_spread`; growth-oriented when conditions are ideal.
- **Profile recommendation** — Suggests `profit_mode` when market is favorable with low vol, high liquidity, and a tight book.
- **GUI** — “Suggested profile” panel wording; `profit_mode` in profile selector.

---

## [1.3.4] — 2026-05-29 (`mainnet-live`)

**Theme:** Session P&L clarity — MTM aligned with cycle log portfolio.

### Added

- **Session MTM P&L** — Mark-to-market since engine start (`session_baseline_portfolio_xrp` + `session_pnl_mtm_xrp`).
- **Balance Δ P&L** — Wallet balance change only (`session_pnl_balance_xrp`); labeled separately in GUI.
- **`docs/STRATEGY_MANUAL.md`** — Decision stack, inventory vs defensive logic, session accounting.
- **Tests** — `tests/test_session_pnl.py`.

### Changed

- **GUI** — Header and Dashboard show both P&L metrics with tooltips; History tab shows session start portfolio.
- **`session_pnl_xrp_estimate`** — Now mirrors MTM P&L for backward compatibility.

---

## [1.3.3] — 2026-05-29 (`mainnet-live`)

**Theme:** Live spread-check stability — bid touch boundary and GUI false failures.

### Fixed

- **Bid touch clamp** — Quotes stay 0.03% inside the max-worse-than-touch limit (avoids float rounding at exactly -0.50%).
- **Spread validation tolerance** — Small boundary slack so clamped quotes do not flicker fail.
- **GUI spread panel** — Shows engine-persisted spread check from last cycle instead of recomputing stale quotes vs a moved book.

### Added

- **Tests** — Bid-at-limit and bid-clamp validation cases in `test_quote_validation.py` / `test_order_clamp.py`.

---

## [1.3.2] — 2026-05-29 (`mainnet-pilot`)

**Theme:** Profile-owned edge, reliable engine stop on Windows, mainnet dry-run validated.

### Added

- **Profile-owned min edge** — Each profile sets `min_edge_pct` (`safe` 0.12%, `tight_spread` 0.08%, etc.); `core/profile_edge.py` for stable imports.
- **Edge strictness** — `edge_strictness` (0.85 / 1.0 / 1.15) and optional `dynamic_min_edge_enabled` in config and GUI.
- **`resolve_effective_min_edge_pct()`** — Combines profile baseline, strictness, and optional book-based cap.
- **Tests** — `test_engine_control.py`, `test_order_clamp.py`.

### Fixed

- **Stop Bot (Windows)** — Kills venv launcher + child Python (`engine.parent.pid`, process scan, `logs/engine.stop` graceful flag).
- **GUI import** — `profile_min_edge_pct` via `core/profile_edge.py`; lazy `gui/__init__.py` so `engine_control` imports do not load Streamlit.
- **Drawdown slider** — GUI range 2–25%, default 10% (5% was too tight for MM).

### Changed

- **Legacy `min_edge_pct` in YAML** — Migrates to `edge_strictness` on load.
- **Defensive quoting GUI** — Strictness selectbox, dynamic edge toggle, effective edge preview.

---

## [1.3.1] — 2026-05-29 (`mainnet-pilot`)

**Theme:** Spread validation fix — competitive asks on mainnet without blowing past the book.

### Fixed

- **Book-pressure scaling** — Was ~100× too large, stacking defensive spread adds (~2.4% off book).
- **Profile spread applied once** — No double application in quote decision.
- **XRP-only mode** — Competitive asks; no ask widening from book pressure/momentum when acquiring RLUSD.
- **Edge guard** — Shrinks size only (does not widen spread into spread_check failure).
- **Book-touch clamp** — `_clamp_quote_price` in `order_manager` keeps quotes near live touch.
- **Missing import** — `evaluate_preflight` restored in `trading_engine.py`.

---

## [1.3.0] — 2026-05-29 (`mainnet-pilot`)

**Theme:** Professional defensive market maker — inventory steering, adverse selection, book pressure, and operator transparency.

### Added

- **Market microstructure** (`strategy/market_microstructure.py`) — Momentum tiers (mild → extreme with side pause), book depth imbalance protection, market-edge filter vs live book spread.
- **Inventory balance advisory** (`strategy/inventory_balance.py`) — RLUSD/XRP steering guidance for XRP-only and two-sided modes (advisory, no auto-swap).
- **Fill quality tracker** (`strategy/fill_quality.py`) — Rolling markout proxy from balance-delta fills; dampens size/spread after toxic fills.
- **Reservation-price skew** — Per-side anchor shifts in `OrderManager` for gradual inventory steering.
- **GUI** — Prominent dry-run / mainnet-live banners, defensive MM metrics (edge, fill quality, pause flags, rebalance advice).
- **Tests** — `test_defensive_mm.py`.

### Changed

- **Profiles** — `safe`, `high_volatility`, `thin_liquidity`, and `tight_spread` now diverge dramatically in spread, size, skew strength, and edge requirements.
- **Inventory skew** — Continuous steering (not only beyond ±12% deviation); slight imbalance still adjusts quotes.
- **Quote decision engine** — Integrates profile baseline, book pressure, momentum tiers, market edge, and fill quality in one decision summary.
- **Runtime state** — Exposes adverse selection tier, book pressure, market edge, fill quality, rebalance advice, pause flags.

---

## [1.2.1] — 2026-05-29 (`mainnet-prep` → `mainnet-pilot`)

**Theme:** Mainnet readiness — live book validation, safe spreads, and operator gates before real orders.

### Added

- **Live spread check** (`utils/quote_validation.py`) — Each cycle compares planned quotes to live best bid/ask; blocks live placement when checks fail.
- **RPC health** (`utils/rpc_health.py`) — Retries on `amendmentBlocked`; default mainnet RPC `https://s1.ripple.com:51234`.
- **Xaman / `sn...` wallet support** (`utils/wallet_credentials.py`) — Correct secp256k1 derivation for Secret Numbers encoding.
- **GUI spread panel** — Dashboard and History show validation table; computes from runtime when engine is stale.
- **Live spread guard** controls — `max_quote_worse_than_touch_pct`, `max_half_spread_from_mid_pct`, block live on fail.
- **Tests** — `test_quote_spreads.py`, `test_quote_validation.py`.

### Fixed

- **Inventory skew** — Capped per-side spread adds (was `deviation × 40`, producing ~8% off-market quotes).
- **Spread display** — Profile spreads no longer blend inventory skew into symmetric “effective spread” table.
- **Streamlit** — Spread check visible after cycles; table/metric left alignment; no `DeltaGenerator` leak on trust-line button.
- **History tab** — Live refresh for price chart and spread data.

### Changed

- **Engine** — Restores price history across restarts; records price tick every cycle with valid mid.
- **Operator manual** — Mainnet go-live gate, spread check troubleshooting, RPC notes.

---

## [1.2.0] — 2026-05-29 (`mainnet-prep` branch)

**Theme:** Defensive market-making — condition-aware quoting, profile recommendations, and kill-switch reliability.

### Added

- **Market condition assessment** (`core/market_conditions.py`) — Favorable / Neutral / Defensive / Hostile tiers from volatility, liquidity, and book spread; health score and profile recommendation.
- **Dynamic quote decisions** (`strategy/quote_decision.py`) — Inventory skew, minimum edge guard, adverse-selection (mid momentum), spread/size multipliers per condition.
- **Enhanced profiles** — Each profile now sets size, aggression, inventory skew strength, and spread floor (not just spread multipliers).
- **GUI market panel** — Top-of-page indicator: profile, market condition, vol, liquidity, spread; profile recommendation with Apply button.
- **Operating mode banners** — Clear DRY-RUN / LIVE testnet / MAINNET LIVE labels.
- **Defensive quoting controls** — Minimum edge %, optional auto profile switching after operator idle time.
- **“Why these quotes?”** — Dashboard caption from engine decision summary.
- **Operator activity tracking** — For conservative auto profile switching (`logs/operator_activity.json`).

### Fixed

- **Kill switch clear** — Running engine reloads kill state from disk each cycle; clear syncs `runtime_state.json` and resets drawdown baseline.
- **GUI Clear kill switch** — Reruns page after successful clear so status updates immediately.

### Changed

- **Order manager** — Uses `QuoteAdjustments` instead of legacy inventory skew helper; per-side spread and size from decision logic.
- **Runtime state** — Persists market condition fields, recommendation, inventory label, momentum, and quote decision summary for GUI.
- **Operator manual** — Documents market conditions, defensive controls, and profile recommendation.

---

## [1.1.0] — 2026-05-28 (`testnet` branch)

**Theme:** Operator-ready testnet — new GUI, funding tools, tax CSV, and ledger fixes.

### Added

- **Tabbed GUI** — Dashboard, Controls, Bot Account, Advanced, History (less clutter, less screen flashing).
- **Logo** — `Xledermate.jpg` in header and sidebar.
- **Live dashboard refresh** — Updates prices and balances every 5s without reloading the whole page.
- **Send / withdraw** — Move XRP or RLUSD from the bot to another address (GUI + `python main.py --mode send`).
- **RLUSD trust line** — `setup-trust` CLI and GUI button.
- **Telegram alerts** — Config in Advanced tab; test message button.
- **Trade & tax CSV** — `logs/trades_YYYY-MM.csv` for BUY, SELL, TRANSFER, MAJOR, and OFFER_REFRESH events.
- **Fill detection** — Infers buy/sell between engine cycles when live trading (not dry-run).
- **XRP-only funding mode** — Start with XRP; place ask quotes until you hold RLUSD.
- **Preflight checks** — Trust line, balances, mid price, order sizes each cycle.
- **Portfolio drawdown** and **persistent kill switch** with offer cancel on live emergency.
- **Portfolio snapshots** — `logs/portfolio_snapshots.csv` each cycle.
- **Engine lifecycle** — Stop duplicate engines; PID file; `stop_all_engines()` from GUI.

### Fixed

- **Order book pricing** — Mid/bid/ask now RLUSD per XRP (was raw XRPL `quality` / bogus ~249M).
- **Order manager budgets** — Bids lock RLUSD, asks lock XRP (was reversed).
- **BotConfig YAML load** — Safe load for new fields (`rlusd_issuer_testnet`, etc.).
- **GUI white-screen bug** — Fragment refresh no longer wipes the page after Start Bot.
- **Balance display** — XRP and RLUSD on separate lines so large balances fit.

### Changed

- **README** — Testnet section, trade log docs.
- **Operator manual** — See `docs/OPERATOR_MANUAL.md` (plain-English guide).

---

## [1.0.0] — Initial baseline (`main`)

- XRPL XRP/RLUSD market-making engine (dry-run default).
- Bot Account–only risk model; profile-based spreads (`safe`, `high_volatility`, etc.).
- Streamlit GUI (single-page), engine loop, order refresh, basic runtime state.
- Testnet connector, perception layer, Avellaneda-style spread engine.

---

## How we got here (short story)

1. **v1.0.0** — Core bot: engine, quotes, first GUI, testnet connector.  
2. **Pricing fire drill** — Testnet mid looked like `249000000`; fixed book parsing and killed duplicate engines.  
3. **Testnet hardening (ffb6054)** — Preflight, kill switch, drawdown, portfolio CSV.  
4. **v1.1.0** — Real operator UX: tabs, logo, fund/send, Telegram, tax CSV, trust line, and everything above.  
5. **v1.2.0 (mainnet-prep)** — Defensive MM decision logic, market conditions GUI, auto profile switching, kill-switch fix.  
6. **v1.3.0–1.3.2 (mainnet-pilot)** — Full defensive MM stack, spread-check fix, profile edge + Windows stop fix; 10-cycle mainnet dry-run gate passed.  
7. **v1.3.3 (mainnet-live)** — First live orders; spread-check boundary fix for two-sided bids + GUI display fix.

**Next likely step:** Continue small live pilot; rebalance toward RLUSD for tighter two-sided quoting.
