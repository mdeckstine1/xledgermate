# WebSocket book probe — captured results (2026-06-05)

**Branch:** `grok-ws-feed` · **Node:** `wss://s1.ripple.com:51233` / `https://s1.ripple.com:51234` · **Pair:** XRP/RLUSD mainnet  
**Status:** Sandbox validated locally — **not** deployed to VPS. Gate 2 stays HTTP poll.

Handoff summary: [groks input/FOR_AI_AND_FUTURE_SESSIONS.md](../../groks%20input/FOR_AI_AND_FUTURE_SESSIONS.md) §3b.

---

## Commits (reference)

| Commit | What |
|--------|------|
| `5934a9d` | Initial `experimental/ws_feed/` sandbox |
| `74e89fd` | RLUSD hex + `SubscribeBook.taker` |
| `0f918ad` | `--verbose`, parse `tx_json`/`tx` (not `transaction` only) |

---

## Run A — 10 min verbose (parser broken)

**Command:** `run_probe --seconds 600 --verbose`  
**Log:** `logs/ws_probe_10min_verbose.log`

| Metric | Result |
|--------|--------|
| Duration | ~603 s |
| WS frames | 2,003 (~3.3/s) |
| `book_apply` | **0** |
| Frame labels | `transaction:?` × 2002 (body in `tx`/`tx_json`, not read) |
| Final WS mid | 1.100789 (+3.6 bps vs HTTP) |
| WS book age | **13.3 s stale** (HTTP refresh only) |

**Lesson:** High frame volume ≠ useful book; wrong tx key made WS a no-op.

---

## Run B — 3 min verbose (parser fixed) ✅

**Command:** `run_probe --seconds 180 --verbose --summary-interval 30`  
**Date:** 2026-06-05 ~14:02–14:05 UTC (local)

| Metric | Result |
|--------|--------|
| Duration | ~183 s |
| WS frames | 543 (~3.0/s) |
| `book_apply` | **519** |
| Offers extracted | **868** |
| Tx mix | OfferCreate 456, OfferCancel 63, Payment 23, subscribe ack 1 |
| Final WS mid | 1.089863 |
| Final HTTP mid | 1.089420 |
| Drift | **+4.1 bps** |
| WS book age | **2.7 s** |

**Early behavior:** Mid moved on WS within seconds of subscribe (e.g. 1.096072 → 1.094183 on OfferCreate burst) without waiting for HTTP poll.

---

## Run C — 3 min summaries only (parser fixed) ✅

**Command:** `run_probe --seconds 180 --summary-interval 30` (no `--verbose`)

| Time | Frames | book_apply | WS mid | HTTP mid | Drift |
|------|--------|------------|--------|----------|-------|
| 33s | 91 | 87 | 1.087500 | 1.087740 | −2.2 bps |
| 63s | 175 | 168 | 1.086305 | 1.086560 | −2.3 bps |
| 94s | 286 | 273 | 1.086488 | 1.085810 | +6.2 bps |
| 124s | 451 | 437 | 1.088260 | 1.089775 | −13.9 bps |
| 155s | 548 | 532 | 1.091336 | 1.091185 | +1.4 bps |
| **Final** | **660** | **631** | **1.092051** | **1.092147** | **−0.9 bps** |

| Metric | Result |
|--------|--------|
| Tx mix (final) | OfferCreate 575, OfferCancel 56, Payment 28 |
| WS book age (final) | **0.4 s** |
| HTTP polls | 12 (~15 s interval) |

**Lesson:** Incremental offer patches can drift ±10 bps mid-run; end-state aligns within ~1 bps. HTTP seed every 45s still useful as reconciliation.

---

## Comparison: poll vs WS (Gate 2 context)

| | HTTP poll (production) | WS subscribe (sandbox) |
|--|------------------------|-------------------------|
| Typical interval | ~15 s book / ~45 s full refresh | ~3 frames/s on active RLUSD book |
| Latency (one-shot BookOffers) | ~1.0–1.3 s | ~0.6–0.9 s |
| Engine wired | Yes (VPS) | No |
| Book model | Full `BookOffers` depth | Per-tx offer deltas + partial state |

---

## Known gaps (next phase)

1. **Subscribe snapshots** — Initial `response:book_snapshot` rarely seen; rely on HTTP seed + deltas. Parse both subscribe responses (bid + ask books).
2. **Book reconciliation** — Periodic full HTTP refresh or snapshot merge; cap drift vs HTTP (target &lt; 5 bps before quoting).
3. **Incremental depth** — Current state is price-keyed patches, not full L2; competitive touch needs best bid/ask trust checks (reuse `is_trustworthy_rlusd_mid`).
4. **Engine adapter** — `book_feed_mode` flag in `trading_engine`; default `poll` on VPS until operator sign-off post–Gate 2.
5. **Noise** — Payment txs on book stream ignored (`offers_applied=0`); OK.

---

## Probe commands (repeat)

```powershell
cd C:\Users\micha\xledgermate
git checkout grok-ws-feed
.\.venv\Scripts\python.exe -m experimental.ws_feed.run_probe --seconds 180 --summary-interval 30
.\.venv\Scripts\python.exe -m experimental.ws_feed.run_probe --seconds 180 --verbose --summary-interval 30
```

---

## Tier 3 integration checklist (after Gate 2)

- [ ] Implement `BookFeed` protocol + `WsBookFeed` behind config flag
- [ ] Unit tests for `tx_json` / snapshot responses
- [ ] 30+ min probe: max drift, reconnect, stale-book guard
- [ ] Operator opt-in; merge `grok-ws-feed` → collab branch
- [ ] VPS deploy only with explicit Tier 3 schedule (not during Gate 2 pilot)