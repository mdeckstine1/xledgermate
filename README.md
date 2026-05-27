# XLedgerMate

XRPL XRP/RLUSD market-making bot (v1) focused on:

- strict risk-capital isolation (Bot Account only)
- transparent perception (volatility, liquidity, effective spreads)
- profile-based control (`safe`, `high_volatility`, `thin_liquidity`, `tight_spread`)

## Project layout

```text
xledgermate/
├── main.py                 # App entrypoint
├── VERSION                 # Release version (v1.0.0)
├── requirements.txt
├── config/                 # Settings loader + example config
├── core/                   # Perception, profiles, decision log, version
├── connectors/             # XRPL connectivity (testnet)
├── strategy/               # Spread engine
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

3. Run (two terminals recommended):

   - Trading engine (continuous loop): `python main.py --mode engine`
   - Single test cycle: `python main.py --mode once`
   - GUI (control panel): `python main.py --mode gui`

   In Cursor, use **Terminal → Run Task**:
   - **XLedgerMate: Run Engine**
   - **XLedgerMate: Run One Cycle**
   - **XLedgerMate: Run GUI**

4. Safety defaults:

   - `dry_run: true` logs quote intents without submitting orders
   - Set `dry_run: false` only when ready for live order placement on Bot Account

## Branches

- `main` — stable baseline on GitHub
- `development` — active build branch for phased work

## Versioning

- Current version: `1.0.0` (`VERSION` file)
- Runtime: `core.version.VERSION`
