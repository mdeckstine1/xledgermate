# XLedgerMate

XRPL XRP/RLUSD market-making bot (v1) focused on:

- strict risk-capital isolation (Bot Account only)
- transparent perception (volatility, liquidity, effective spreads)
- profile-based control (`safe`, `high_volatility`, `thin_liquidity`, `tight_spread`, `profit_mode`)

## Project layout

```text
xledgermate/
├── main.py                 # App entrypoint
├── VERSION                 # Release version (1.4.4)
├── CHANGELOG.md            # Version history
├── docs/OPERATOR_MANUAL.md # Non-technical operator guide
├── requirements.txt
├── config/                 # Settings loader + example config
├── core/                   # Perception, market conditions, runtime state, version
├── connectors/             # XRPL connectivity (testnet/mainnet)
├── strategy/               # Spread engine + quote decision logic
├── engine/                 # Trading loop + quote planning
├── risk/                   # Drawdown + inventory controls
├── monitoring/             # Alerts + CSV logging
├── gui/                    # Streamlit operator UI
└── utils/                  # Logging + helpers
```

## Quick start

1. Create and use the virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Create local config from the example:

   ```powershell
   copy config\config.example.yaml config\config.yaml
   ```

   Edit `config/config.yaml` and set:

   - `bot_account_address`
   - `bot_secret_key` (never commit real secrets)
   - network mode:
     - `testnet: true` for development
     - `testnet: false` for mainnet
   - RPC endpoints:
     - `xrpl_testnet_rpc_url`
     - `xrpl_mainnet_rpc_url`
     - optional `private_node_url` (overrides both)

3. Run everything (one step):

   - Double-click `run.bat`, or in terminal: `.\run.ps1`
   - In Cursor: **Terminal → Run Task → XLedgerMate: Run All**

   This opens the engine and GUI in separate windows.

4. Or run components separately:

   - Trading engine (continuous loop): `python main.py --mode engine`
   - Single test cycle: `python main.py --mode once`
   - GUI (control panel): `python main.py --mode gui`

   In Cursor, use **Terminal → Run Task**:
   - **XLedgerMate: Run All**
   - **XLedgerMate: Run Engine**
   - **XLedgerMate: Run One Cycle**
   - **XLedgerMate: Run GUI**

5. Safety defaults:

   - `dry_run: true` logs quote intents without submitting orders
   - Set `dry_run: false` only when ready for live order placement on Bot Account

## Branches

- `main` — stable baseline on GitHub
- `tier-2-polish` — **current mainnet pilot** (v1.4.4: Tier 1 + Gate 1 complete; **Gate 2 `tight_spread`** in progress)
- `development` — integration branch for phased work
- `testnet` — testnet hardening (preflight, kill switch, portfolio drawdown, trust line tools)
- `mainnet-prep` / `mainnet-pilot` — earlier mainnet phases (merged into tier-2 line)

## Mainnet prep (v1.2.1)

Before **live** mainnet (`dry_run: false`):

1. `testnet: false`, RPC `https://s1.ripple.com:51234` (avoid stale `xrplcluster.com` nodes).
2. Credentials: Xaman `sn...` or family seed `s...` (see Bot Account tab).
3. Run **dry-run** until Dashboard **Spread check OK** for many cycles in a row.
4. **Stop Bot** → **Start Bot** after pulling new code.
5. Follow the **Mainnet go-live gate** in [`docs/OPERATOR_MANUAL.md`](docs/OPERATOR_MANUAL.md).

Spread guard settings in **Controls** (`max_quote_worse_than_touch_pct`, etc.) block live placement when quotes are off the book.

## Testnet branch (`testnet`)

Hardening for testnet dry-run and small live tests:

1. **Preflight** each cycle (trust line, balances, mid price, order sizes). Dry-run allows missing trust line with a warning.
2. **Portfolio drawdown** (XRP + RLUSD at mid), persistent **kill switch** (`logs/kill_switch.json`).
3. **Kill switch cancels** open offers when live trading is enabled.
4. **Balance caps** on quote sizes vs XRP reserve and RLUSD balance.
5. **TX validation** (`tesSUCCESS` required on submit).
6. **Portfolio log**: `logs/portfolio_snapshots.csv` each cycle.
7. **Tax / trade log**: `logs/trades_YYYY-MM.csv` — BUY/SELL fills (live only), TRANSFER (sends), MAJOR (kill switch, engine start), OFFER_REFRESH (live quote cycles). Not written in dry-run except MAJOR on engine start.

CLI helpers:

```powershell
python main.py --mode once
python main.py --mode setup-trust
python main.py --mode cancel-offers
python main.py --mode clear-kill
```

Before **live** testnet (`dry_run: false`): run `setup-trust`, fund RLUSD, set non-zero `order_sizes` in config.

## Versioning

- Current version: see [`VERSION`](VERSION) (e.g. **1.4.4**)
- Release notes: [`CHANGELOG.md`](CHANGELOG.md)
- Operator guide: [`docs/OPERATOR_MANUAL.md`](docs/OPERATOR_MANUAL.md)
- Strategy + gates: [`docs/STRATEGY_MANUAL.md`](docs/STRATEGY_MANUAL.md), [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
- Mainnet pilot: [`docs/MAINNET_PILOT.md`](docs/MAINNET_PILOT.md)
- Session metrics: `python scripts/weekly_skim_report.py`, `python scripts/analyze_session.py`
- Runtime: `core.version.VERSION`
