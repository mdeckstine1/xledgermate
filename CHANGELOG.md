# Changelog

All notable changes to XLedgerMate are documented here.  
Version numbers follow [Semantic Versioning](https://semver.org/) where practical.

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
