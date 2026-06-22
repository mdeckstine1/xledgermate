# Trading Bot Alpha — Phase 4 Entry + Integration

**Version:** 1.0.0  
**Branch:** `alpha`

## What shipped

Phase 4 completes the MVP buy → bracket → OCO cycle with entry execution and a trading loop.

| Module | Role |
|--------|------|
| `alpha/decision/engine.py` | Edge-aware buy signals, inventory guards, risk-per-trade sizing |
| `alpha/runtime/executor.py` | `EntryExecutor` — places limits, registers pending buys |
| `alpha/runtime/application.py` | `run_trading_cycle`, `run_trading_loop` |
| `alpha/__main__.py` | `python -m alpha run` CLI |

## Entry logic (MVP)

**Buy signal** when all pass:

1. `trading_enabled` and preflight OK, kill switch off
2. Inventory weakness: `deviation <= -alpha_weakness_deviation`
3. Not blocked: `deviation <= alpha_max_inventory_imbalance_pct` (too XRP-heavy)
4. Pending buys `< alpha_max_pending_buys`
5. Edge: limit price `mid × (1 - alpha_buy_limit_offset_pct)` with edge ≥ `alpha_min_edge_threshold_pct`
6. Ask depth ≥ `min_order_size_xrp`
7. Size capped by: base size × skew, ask depth, `risk_per_trade_pct` × portfolio, `max_leg_size_pct_of_capital`

**Strength sell** (inventory unload): direct limit ask — no bracket (TP/SL only on bought XRP).

## Integration flow

```
run_trading_cycle
  → sync_brackets (fills → TP/SL, OCO)
  → DecisionEngine.evaluate
  → EntryExecutor.execute
       PLACE_BID → place_limit_buy_xrp → register_pending_buy
       (on fill) sync_brackets → place TP + SL
```

## CLI

```bash
python -m alpha status           # read-only snapshot
python -m alpha run --once       # one trading cycle
python -m alpha run              # loop (interval: alpha_cycle_interval_seconds)
python -m alpha run --max-cycles 10
```

## Config keys (Phase 4)

| Key | Default | Purpose |
|-----|---------|---------|
| `alpha_risk_per_trade_pct` | `0.5` | Max entry size as % of portfolio |
| `alpha_min_edge_threshold_pct` | `0.08` | Min edge vs mid to buy |
| `alpha_buy_limit_offset_pct` | `0.15` | Limit buy % below mid |
| `alpha_max_inventory_imbalance_pct` | `0.10` | Block buys when XRP-heavy |
| `alpha_max_pending_buys` | `1` | Max concurrent pending buys |
| `alpha_cycle_interval_seconds` | `60` | Loop interval |

## Safety

- `dry_run: true` — executor logs `entry_execute_dry_run`, no ledger writes
- Conservative defaults for mainnet
- Existing kill switch, drawdown, preflight unchanged

## MVP complete — ready for polish

- Core buy/sell cycle with brackets: **yes**
- Telegram-rich reports, advanced structure detection, GUI: **future**
- Trailing SL/TP: placeholder (`bracket_trailing_enabled`)

See Phase 3: `docs/TRADING_BOT_ALPHA_PHASE3.md`.
