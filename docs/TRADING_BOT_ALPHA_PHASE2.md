# Trading Bot Alpha — Phase 2 Ledger + Decision

**Version:** 1.0.0 (`alpha/version.py`)  
**Branch:** `alpha`

## What shipped

Phase 2 extends the ledger boundary and decision engine for value accumulation (not legacy MM quoting).

| Module | Role |
|--------|------|
| `alpha/ledger/liquidity.py` | Slippage-aware depth from order book snapshots |
| `alpha/ledger/ws_session.py` | Optional WebSocket account transaction subscription |
| `alpha/ledger/xrpl_adapter.py` | Book snapshot, liquidity depth, gated limit orders |
| `alpha/ledger/interface.py` | Extended `LedgerInterface` protocol |
| `alpha/decision/engine.py` | Weakness → bid, strength → ask; depth-capped sizing |
| `alpha/types.py` | `OrderBookSnapshot`, `LiquidityDepth`, `AccountSnapshot`, etc. |

## Operator usage

Unchanged CLI:

```bash
python -m alpha status
python -m alpha status --no-telegram
```

Each status cycle now:

1. Connects optional WS account stream (`alpha_ws_enabled`)
2. Fetches order book + liquidity depth
3. Evaluates inventory/risk and emits a decision (may be `PLACE_BID` / `PLACE_ASK` with suggested size/price)
4. Does **not** submit orders via `OrderManager` (Phase 3)

## Config keys (new)

| Key | Default | Purpose |
|-----|---------|---------|
| `alpha_ws_enabled` | `true` | WebSocket account tx subscription |
| `alpha_max_slippage_pct` | `0.50` | Depth walk for sizing cap |
| `alpha_weakness_deviation` | `0.05` | Min ratio below target to bid |
| `alpha_strength_deviation` | `0.05` | Min ratio above target to ask |
| `alpha_base_order_size_xrp` | `50.0` | Conservative base clip |
| `alpha_bid_offset_pct` | `0.02` | Bid price below best bid |
| `alpha_ask_offset_pct` | `0.02` | Ask price above best ask |

## Safety

- `dry_run: true` remains default; `place_limit_*` and `cancel_offer` call `DryRunGuard.require_live()`.
- No secret logging; WS failures fall back to HTTP book reads.
- Mainnet: set `testnet: false`; keep `dry_run: true` until operator is ready.

## Next (Phase 3)

- `OrderManager`: bracket (TP + SL), OCO, selective trailing
- Wire decisions through order lifecycle (not ledger helpers only)
- Long-running Alpha loop / deploy unit

See `PROJECT_INSTRUCTIONS.md` and `docs/TRADING_BOT_ALPHA_PHASE1.md`.
