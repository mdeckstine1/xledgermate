# Trading Bot Alpha — Phase 3 OrderManager + Brackets

**Version:** 1.0.0  
**Branch:** `alpha`

## What shipped

Phase 3 implements application-level bracket management (TP + SL limit sells after buy fill) with OCO cancel of the opposing leg. No legacy MM logic.

| Module | Role |
|--------|------|
| `alpha/orders/manager.py` | `OrderManager` — lifecycle sync, registration, OCO |
| `alpha/orders/bracket.py` | TP/SL price math (RR or fixed %) |
| `alpha/orders/state.py` | `BracketStateStore` — index by buy/leg sequence |
| `alpha/orders/types.py` | State machine enums, `BracketRecord`, events |

## Bracket lifecycle

```
PENDING_BUY → (buy fill) → BRACKET_ACTIVE → TP_FILLED | SL_FILLED
                                    ↓
                         TRAILING_PLACEHOLDER (optional, placeholder)
```

1. **Register** — `register_pending_buy(buy_sequence, size_xrp, entry_price)`
2. **Buy fill** — offer disappears from open offers → place TP + SL limit sells
3. **OCO** — when TP or SL fills (≥ `min_fill_size_xrp_for_oco`), cancel opposing leg
4. **Partial fills** — `partial_fill_mode`:
   - `wait_full` — bracket legs placed only after buy offer fully gone
   - `proportional` — bracket sized to filled XRP while buy still open

## Pricing

- **SL:** `entry * (1 - initial_stop_loss_pct)`
- **TP (RR mode, default):** `entry * (1 + initial_stop_loss_pct * take_profit_rr)` when `take_profit_rr > 0`
- **TP (fixed):** `entry * (1 + take_profit_pct)` when `take_profit_rr <= 0`

## Config keys

| Key | Default | Purpose |
|-----|---------|---------|
| `initial_stop_loss_pct` | `0.015` | SL distance below entry |
| `take_profit_pct` | `0.03` | Fixed TP % (when RR off) |
| `take_profit_rr` | `2.0` | Risk-reward multiplier for TP |
| `partial_fill_mode` | `wait_full` | `wait_full` \| `proportional` |
| `min_fill_size_xrp_for_oco` | `0.5` | Min leg fill before OCO cancel |
| `bracket_trailing_enabled` | `false` | Placeholder → `TRAILING_PLACEHOLDER` mode |

## Safety

- All writes via `LedgerInterface` + `DryRunGuard`
- `cancel_all` logs intent in dry-run without ledger mutation
- Structured logs: `bracket_register`, `bracket_place_legs`, `bracket_leg_fill`, `bracket_oco_cancel`

## Tests

```bash
python -m pytest tests/test_alpha_foundation.py tests/test_alpha_phase2.py tests/test_alpha_order_manager.py -q
```

## Phase 4 readiness

**Ready**
- Bracket state machine + OCO
- Ledger integration for place/cancel/sync
- Decision engine emits entry signals (Phase 2)
- `AlphaApplication.run_status_cycle` calls `sync_brackets()`

**Phase 4 scope**
- Wire `DecisionEngine` → `register_pending_buy` / live entry submission
- Long-running trading loop
- Real trailing SL/TP (replace placeholder)
- Fill detection via WS account stream (refine cancelled-buy vs fill)

See `PROJECT_INSTRUCTIONS.md` and Phase 2 doc: `docs/TRADING_BOT_ALPHA_PHASE2.md`.
