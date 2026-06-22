# Trading Bot Alpha — Phase 1 Foundation

**Version:** 1.0.0 (`alpha/version.py`)  
**Branch:** `alpha`

## What shipped

Phase 1 adds a new `alpha/` package that wraps existing infrastructure without porting legacy MM/quoting logic.

| Module | Role |
|--------|------|
| `alpha/ledger/` | `LedgerInterface` + `XrplLedgerAdapter` over `XRPLConnector` |
| `alpha/inventory/` | `InventoryManager` — skew vs `inventory_target_xrp_ratio` |
| `alpha/risk/` | `RiskEngine` — kill switch, drawdown, `evaluate_preflight` |
| `alpha/reporting/` | `ReportingService` — Telegram + structured console report |
| `alpha/orders/` | `OrderManager` placeholder (sync offers only; bracket in Phase 2) |
| `alpha/decision/` | `DecisionEngine` placeholder (always HOLD in Phase 1) |
| `alpha/dry_run.py` | `DryRunGuard` — all live mutations must pass `require_live()` |
| `alpha/config_validator.py` | Alpha validation on top of `BotConfig.load()` |

## Operator usage

```bash
python -m alpha status              # one read-only cycle + optional Telegram
python -m alpha status --no-telegram
```

Config and secrets are unchanged: `config/config.yaml` + `config/credentials.local.yaml` via existing `BotConfig.load()`.

## Safety

- `dry_run: true` remains the default in YAML.
- Phase 1 performs **no order submission**; `OrderManager.submit_bracket` / `cancel_all` raise `NotImplementedError` after dry-run gate.
- Mainnet warnings surface when `testnet: false` or `dry_run: false`.

## Next (Phase 2 — shipped)

See `docs/TRADING_BOT_ALPHA_PHASE2.md` for ledger depth, WS account stream, and decision sizing.

## Later (Phase 3)

- OrderManager: application-level bracket (TP + SL), OCO, selective trailing
- Long-running loop / deploy unit for Alpha (separate from legacy `ws_pure_engine`)

See `PROJECT_INSTRUCTIONS.md` for full project rules.
