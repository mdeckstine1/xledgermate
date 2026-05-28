# Changelog

All notable changes to XLedgerMate are documented here.  
Version numbers follow [Semantic Versioning](https://semver.org/) where practical.

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
4. **v1.1.0 (this release)** — Real operator UX: tabs, logo, fund/send, Telegram, tax CSV, trust line, and everything above.

**Next likely step:** Soak test on testnet (small live size), then a `mainnet-prep` branch.
