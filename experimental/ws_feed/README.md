# WebSocket book feed (Tier 3 sandbox)

**Not wired to production.** The live Gate 2 stack on the VPS keeps using HTTP `BookOffers` polling via `engine/trading_engine.py` → `XRPLConnector.fetch_xrp_rlusd_order_book()`.

This folder is an isolated lab to prototype a WebSocket book feed that reuses the same normalization and mid/spread logic as `connectors/xrpl_connector.py`, without changing `main.py --mode engine`.

## Layout

| File | Role |
|------|------|
| `network_urls.py` | Map `config.resolved_rpc_url()` → `wss://…:51233` |
| `pair_books.py` | RLUSD/XRP `SubscribeBook` pair (both sides) |
| `book_messages.py` | Parse XRPL WS book/transaction payloads → offer rows |
| `book_state.py` | In-memory bid/ask levels from snapshots + deltas |
| `http_poll_feed.py` | Thin wrapper around existing HTTP fetch (baseline) |
| `ws_book_feed.py` | Subscribe + listen loop + HTTP refresh fallback |
| `run_probe.py` | Standalone CLI: compare HTTP vs WS mids/latency |

## Git branch

Work happens on **`grok-ws-feed`** (branched from `grok-tier-2-collab`). Merge into the active collab branch only after probe + tests pass and the operator opts in.

## Run locally (no engine, no VPS deploy)

From repo root with venv and `config/config.yaml`:

```bash
python -m experimental.ws_feed.run_probe --seconds 90
python -m experimental.ws_feed.run_probe --http-only --seconds 30
```

Requires network access to your configured rippled node. Does not place orders or touch `logs/kill_switch.json`.

## Integration plan (later)

1. **Probe** — `run_probe` shows stable WS mids vs HTTP on mainnet/testnet.
2. **Adapter** — `BookFeed` protocol consumed by a feature flag in `trading_engine` (e.g. `book_feed_mode: poll|ws|ws_with_http_fallback`).
3. **VPS** — only after Gate 2 run completes; systemd stays on poll until then.

## VPS rule

Do **not** copy this tree into the active `/root/xledgermate` systemd unit or enable WS in `config.yaml` on `188.245.50.229` until Tier 3 is explicitly scheduled.