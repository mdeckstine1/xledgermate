# WebSocket book feed + Pure A-S + Real Grok (experimental / committed future path)

**Not wired to production (sacred gated long-run on VPS still uses HTTP poll + hard gates).** This is the isolated lab + live observation surface for the future architecture: WS BookFeed + replicated long-run wiring + **pure Avellaneda-Stoikov** (built-in protections only) + competitor pressure + **advisory real xAI Grok** for exploitation analysis (holes, tactics, positioning to increase skim / fill the value bag).

**Task checklist:** [`../../docs/PURE_AS_CRITICAL_PATH.md`](../../docs/PURE_AS_CRITICAL_PATH.md). **Run commands:** [`../../groks input/CURSOR_HANDOFF_ROADMAP.md`](../../groks%20input/CURSOR_HANDOFF_ROADMAP.md).

## Live Tester + HUD (primary artifact now)

The dedicated real-time surface is `live_pure_as_tester.py --serve-hud` (writes `logs/ws_as_demo_runtime.json` for analysis / old GUI loading).

Run (from repo root, in venv):
```powershell
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose --intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-3
```
- Open http://127.0.0.1:8765
- Intelligence tab: live competitor scrape + pressure + "Analyze with AI" (real grok-3 exploitation prompts).
- Per-sample Grok (lighter) + on-demand rich analysis (holes/tactics/skim/positioning) are wired. Strictly advisory.

**Status (2026-06-10, cash added, HUD live):** Pure A-S correctly 0-quotes on tight books (reservation/opt spread math), 5 competitors tracked with real activity, pressure ~0.4, Grok-3 working, unlimited runs (limit removed). See WS_AS_MANUAL.md and the CURSOR_HANDOFF_ROADMAP for details + latest runtime snapshots.

## Probe results (historical, 2026-06-05)

**[PROBE_RESULTS.md](PROBE_RESULTS.md)** — captured 10 min / 3 min runs, metrics, Tier 3 checklist. Sandbox **validated** (−0.9 bps vs HTTP at 3 min); **not** on VPS. (The focus has since moved to the full live pure A-S + HUD + Grok exploitation surface above.)

## Layout

| File | Role |
|------|------|
| `PROBE_RESULTS.md` | Metrics + next-phase checklist for handoff / Tier 3 |
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
python -m experimental.ws_feed.run_probe --seconds 600 --verbose
python -m experimental.ws_feed.run_probe --http-only --seconds 30
```

**`--verbose`:** one log line per WebSocket frame (message type, e.g. `transaction:OfferCreate`, whether book levels were applied, WS mid, staleness). Without it you only see HTTP polls plus a summary every `--summary-interval` seconds (default 60) and a final rollup.

Requires network access to your configured rippled node. Does not place orders or touch `logs/kill_switch.json`.

## Integration plan (later)

1. **Probe** — `run_probe` shows stable WS mids vs HTTP on mainnet/testnet.
2. **Adapter** — `BookFeed` protocol consumed by a feature flag in `trading_engine` (e.g. `book_feed_mode: poll|ws|ws_with_http_fallback`).
3. **VPS** — only after Gate 2 run completes; systemd stays on poll until then.

## VPS rule

Do **not** copy this tree into the active `/root/xledgermate` systemd unit or enable WS in `config.yaml` on `188.245.50.229` until Tier 3 is explicitly scheduled.