# Mainnet pilot branch

**Branch:** `mainnet-pilot`  
**Version:** 1.2.1+  
**Goal:** A short, controlled live mainnet trial on the Bot Account only.

## Scope

- `testnet: false`, `dry_run: false`
- One order level, small `order_sizes` (e.g. 5–10 XRP)
- Spread check must pass every cycle (engine blocks if not)
- Monitor: Dashboard, `logs/trades_YYYY-MM.csv`, `logs/portfolio_snapshots.csv`

## Out of scope (later)

- Full risk capital deployment
- Unattended 24/7 operation without monitoring
- Two-sided quoting until RLUSD balance is meaningful

## Operator checklist

See **Mainnet go-live gate** in [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md).
