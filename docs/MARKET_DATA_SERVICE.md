# Market Data Service (MDS) — development path

**Status:** Design / not in production  
**Audience:** Developers building subscription hosting and shared market + TA infrastructure  
**Not for operators:** See [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) and [`ALPHA_TRADERS_MANUAL.md`](ALPHA_TRADERS_MANUAL.md) for running a single bot.

---

## Purpose

**MDS** is a pair-level service for **XRP / RLUSD mainnet** that owns everything that is **identical for every bot account**:

- L1 order book (bid, ask, mid, spread)
- Rolling tick history (bid / ask / mid / last)
- Multi-timeframe OHLC (SQLite today → shared DB tomorrow)
- Derived market metrics (ATR%, realized vol, regime)
- Optional: precomputed **TA profiles** and **structure** snapshots

**Tenant Alpha engines** keep wallet-specific work: ledger auth, balances, inventory, risk, brackets, decisions, tax CSV, HUD state.

This doc is the **development path** for MDS — phases, extraction map, APIs, deployment, and integration contracts. It is intentionally **not** folded into the trader or operator manuals.

---

## Problem today (per-tenant duplication)

Each `AlphaApplication` instance under `logs/` currently maintains:

| Asset | Path / module | Duplicated per VPS? |
|-------|----------------|---------------------|
| Tick history | `logs/alpha_price_history.json` | `alpha/decision/price_history.py` |
| OHLC cache | `logs/alpha_market.db` | `alpha/decision/ohlc_cache.py` |
| Book fetch | RPC per engine cycle | `alpha/ledger/xrpl_adapter.py` |
| TA compute | In-process each cycle | `alpha/decision/technical_analysis.py` |
| Structure | In-process | `alpha/decision/structure.py` |
| Cycle metrics | Rows in `alpha_market.db` | `alpha/decision/market_metrics.py` |

For **N subscribers** on the same pair, that is **N book polls**, **N warmup periods**, and **N OHLC rebuilds** — cost, drift, and support burden.

---

## Design principles

1. **Pair-level, not account-level** — MDS has **no** `bot_secret_key`, no brackets, no inventory.
2. **One writer** — single process appends ticks and closes OHLC bars; tenants are read-only consumers.
3. **Stale-aware** — tenants must **pause new bids** (or hold) when MDS data is older than SLA; never trade on silent cache.
4. **Profile-based TA** — subscription v1 uses **fixed profiles** (e.g. `family_mid_5m`); custom per-tenant TA TF is a later tier.
5. **Extract, don't rewrite** — Phase 1 moves existing modules behind a service boundary; decision/orders code stays stable.
6. **Dogfood on samurai** — MDS ships on `samurai`; production pins (`samurai-v1.0.x`) pick up only after soak.

---

## Architecture (target)

```text
┌─────────────────────────────────────────────────────────┐
│  MDS (single deployment per network + pair)              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Book ingest │→ │ Tick writer  │→ │ OHLC + metrics  │ │
│  │ (WS or RPC) │  │ price_history│  │ alpha_market.db │ │
│  └─────────────┘  └──────────────┘  └────────┬────────┘ │
│                                               │          │
│  ┌────────────────────────────────────────────▼──────┐  │
│  │ Optional: TA + structure @ standard profiles      │  │
│  └───────────────────────────────────────────────────┘  │
│  HTTP/WS API · health · metrics                          │
└───────────────────────────┬─────────────────────────────┘
                            │ read / subscribe
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Alpha tenant A      Alpha tenant B      Alpha tenant C
   (wallet + HUD)      (wallet + HUD)      (wallet + HUD)
```

---

## Package layout (planned)

```text
alpha/
  market_data/              # NEW — MDS library + service entrypoints
    __init__.py
    ingest.py               # book poll / WS hook (from ledger layer)
    tick_store.py           # wraps price_history persistence
    ohlc_writer.py          # wraps ohlc_cache bar close logic
    metrics.py              # regime / ATR / vol publication
    profiles.py             # FAMILY_MID_5M constants
    server.py               # FastAPI or lightweight HTTP + WS
    client.py               # tenant-side fetch + stale checks
  decision/                 # existing — TA math stays here; MDS calls it
  runtime/
    application.py          # Phase 3: MDS client instead of local OHLC
```

**Service unit (systemd):** `xledgermate-mds.service`  
**Default bind:** `127.0.0.1:8770` (internal); reverse-proxy only if needed.

---

## API sketch (v1)

Read-only JSON. Exact paths may change; tenants pin a **client contract version**.

| Method | Path | Returns |
|--------|------|---------|
| `GET` | `/health` | `{ ok, book_age_ms, last_bar_close_utc, schema_version }` |
| `GET` | `/v1/book` | `OrderBookSnapshot` fields: bid, ask, mid, spread_pct, updated_utc |
| `GET` | `/v1/ticks/meta` | sample interval, sources available, tick count |
| `GET` | `/v1/ohlc?interval_sec=300&limit=200` | `{ interval_sec, bars: [{open,high,low,close,ts}, ...] }` |
| `GET` | `/v1/market/summary` | ATR%, realized vol, regime (from `market_metrics` logic) |
| `GET` | `/v1/ta?profile=family_mid_5m` | `TechnicalAnalysisSnapshot` JSON |
| `GET` | `/v1/structure?profile=family_mid_5m` | `MarketStructureSnapshot` JSON |
| `WS` | `/v1/stream` | `book` events + `bar_closed` per interval |

**Staleness headers:** `X-MDS-Book-Age-Ms`, `X-MDS-Data-Version`.

**Tenant rule:** if `book_age_ms > tenant.mds_max_stale_ms` (config, default 45_000) → treat as **MDS stale**; decision layer holds new bids with reason `mds_stale`.

---

## Standard profiles (subscription v1)

Freeze one profile for Family / hosted tiers — do not expose arbitrary TA TF in v1.

| Profile ID | Candle TF | Price source | Notes |
|------------|-----------|--------------|-------|
| `family_mid_5m` | 300s | mid | Default hosted tier |
| `family_mid_15m` | 900s | mid | Patient / trust phase |
| `dev_ask_5m` | 300s | ask | Parity with current aggressive entry bias |

Profiles map to `BotConfig.alpha_technical_analysis` presets in `alpha/market_data/profiles.py` (not operator-editable on hosted tier).

OHLC intervals maintained by MDS (from `retention_policy.CACHED_INTERVALS_SECONDS`):

`300, 900, 1800, 3600, 7200, 9000` seconds.

---

## Development phases

### Phase 0 — Spec + metrics (no new service)

- [ ] This document reviewed and pinned on `samurai`
- [ ] Define SLA: book refresh ≤ 15s, bar close latency ≤ 2s after boundary
- [ ] Define `mds_stale` decision reason and HUD display (Live Decision card)
- [ ] Add config keys (design only): `alpha_mds_enabled`, `alpha_mds_url`, `alpha_mds_profile`, `alpha_mds_max_stale_ms`

**Exit:** Team agrees Phase 1 scope; no operator doc changes required.

---

### Phase 1 — Shared ingest + OHLC (MDS core)

**Goal:** One process writes ticks + OHLC; one tenant engine reads via `market_data.client` while others can still run legacy local path.

| Task | Source to extract |
|------|-------------------|
| Book poll loop | `alpha/ledger/xrpl_adapter.get_order_book` (no account needed for public book) |
| Append ticks | `price_history.append_book_prices` |
| OHLC live update | `ohlc_cache` bar writer paths |
| Startup rebuild | `ohlc_cache.ensure_ohlc_cache`, `rebuild_all_from_ticks` |
| Retention | `alpha/decision/retention_policy.py` |

**Deliverables:**

- `xledgermate-mds` CLI: `python -m alpha.market_data.server`
- `alpha/market_data/client.py` with `fetch_book()`, `fetch_ohlc()`, `is_stale()`
- Feature flag `alpha_mds_enabled=false` default — **no behavior change** until enabled
- Tests: bar alignment, restart idempotency, stale detection
- `docker-compose.mds.yml` for local dogfood (optional)

**Exit:** Your production bot on VPS can run with `alpha_mds_enabled=true` pointing at local MDS; logs show no local OHLC writes on tenant.

---

### Phase 2 — Shared TA + structure profiles

**Goal:** MDS publishes `TechnicalAnalysisSnapshot` + `MarketStructureSnapshot` for each profile.

| Task | Source |
|------|--------|
| TA compute | `TechnicalAnalysis.analyze()` |
| Structure | `analyze_structure()` |
| Warmup status | `indicator_warmup_status`, `ta_warmup_tick_threshold` |

**Deliverables:**

- `GET /v1/ta?profile=…` and `/v1/structure?profile=…`
- Tenant `_gather_cycle_context` uses client when MDS enabled
- HUD `state_export` can use MDS TA for chart block (same snapshot as engine)

**Exit:** Second tenant on same host starts with **warm TA** (no 48h warmup).

---

### Phase 3 — Multi-tenant hosting default

**Goal:** Subscription provisioning runs **one MDS per pair per region**; each customer VPS (or container) is engine+Hud only.

| Task | Notes |
|------|-------|
| Provisioner sets `alpha_mds_url=http://mds.internal:8770` | Per region |
| Remove duplicate `alpha_market.db` from tenant images | Tenant logs slimmer |
| Monitoring | Prometheus or simple health cron; page if MDS down |
| Backup | MDS SQLite + tick file snapshot daily |

**Exit:** 3+ hosted accounts on one MDS with stable book age and shared TA.

---

### Phase 4 — Hardening (production subscription)

- [ ] MDS HA (warm standby or fast restart from tick file)
- [ ] WS stream for HUD sub-second book line (tenant HUD may still poll MDS HTTP)
- [ ] Rate limits on API
- [ ] Separate testnet MDS instance (never share mainnet/testnet DB)
- [ ] Versioned API (`v1` freeze for tenants)

---

## Tenant integration (AlphaApplication)

Pseudocode for `_gather_cycle_context` after Phase 2:

```python
if config.alpha_mds_enabled:
    snap = mds_client.fetch_snapshot(profile=config.alpha_mds_profile)
    if snap.stale:
        # hold new bids; still sync brackets / risk on wallet data
        ta_snapshot = snap.ta  # may be None
        book = snap.book
    else:
        book = snap.book
        ta_snapshot = snap.ta
        structure = snap.structure
else:
    # existing local path (price_history + ohlc_cache + in-process TA)
    ...
```

**Wallet-bound calls stay local:** balances, open offers, submit tx, bracket sync.

---

## Code extraction map

| Current module | MDS role | Stays in tenant? |
|----------------|----------|------------------|
| `alpha/decision/price_history.py` | Tick store (writer) | Reader optional (chart only) |
| `alpha/decision/ohlc_cache.py` | OHLC writer + DB | No writes when MDS on |
| `alpha/decision/market_metrics.py` | Metrics writer | Read summary from MDS |
| `alpha/decision/technical_analysis.py` | Library | Tenant only if MDS off |
| `alpha/decision/structure.py` | Library | Tenant only if MDS off |
| `alpha/ledger/xrpl_adapter.py` (book) | Ingest | Full adapter stays for account ops |
| `alpha/hud/state_export.py` | Consumer | Uses MDS client for chart/TA block |

**Do not move:** `orders/`, `risk/`, `inventory/`, `operator/`, `pro/`, tax reporting.

---

## Branch and release discipline

| Work | Branch |
|------|--------|
| MDS feature development | `samurai` |
| Tenant MDS client flag | `samurai` |
| Production VPS pin | `samurai-v1.0.x` only after MDS soak + flag default documented |

See [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md). MDS is **not** deployed to frozen pins until Phase 1 exit criteria pass on your live box.

**Commit prefix suggestion:** `mds:` for service-only commits (easier to cherry-pick / revert).

---

## Testing strategy

| Layer | Tests |
|-------|--------|
| OHLC | Bar open/close boundaries, DST-safe UTC, gap repair (`repair_incomplete_bars`) |
| API | Contract tests on `/v1/book`, `/v1/ohlc`, stale headers |
| Integration | Tenant with `alpha_mds_enabled` vs local path — **same** TA scores on recorded tick fixture |
| Failure | Kill MDS → tenant holds with `mds_stale`; brackets still managed |
| Load | 1 MDS feeding 10 mock tenants polling each cycle |

Fixtures: replay tick file from `logs/alpha_price_history.json` on VPS (sanitize before commit).

---

## Deployment sketches

### A — Co-located (first hosted subscribers)

```text
Hetzner VPS
  xledgermate-mds.service     :8770
  xledgermate-alpha-alice.service
  xledgermate-alpha-bob.service
  xledgermate-alpha-hud-alice / bob  (or combined HUD router later)
```

### B — Regional MDS VPS

```text
mds-eu.xledgermate.internal:8770  →  tenant VPSs in EU
```

Tenants need low latency to MDS (&lt; 50ms preferred).

---

## Config keys (planned)

```yaml
# Tenant config.yaml (Phase 1+)
alpha_mds_enabled: false
alpha_mds_url: "http://127.0.0.1:8770"
alpha_mds_profile: family_mid_5m
alpha_mds_max_stale_ms: 45000

# MDS config (separate mds.yaml or env)
mds_network: mainnet
mds_pair: XRP-RLUSD
mds_sample_interval_seconds: 15
mds_book_poll_seconds: 15
mds_data_dir: /var/lib/xledgermate-mds
mds_bind_host: 127.0.0.1
mds_port: 8770
```

---

## Non-goals (v1)

- Multi-pair MDS (ETH, BTC, etc.)
- Per-tenant custom candle intervals on hosted tier
- MDS placing or cancelling orders
- Custody or wallet keys on MDS host
- Operator-facing MDS documentation inside `ALPHA_TRADERS_MANUAL.md`

---

## Open questions

1. **WS vs RPC** for book — reuse `alpha/ledger/ws_session` or poll RPC only for v1?
2. **SQLite vs Postgres** when MDS serves 50+ tenants (SQLite likely fine until then).
3. **HUD chart** — poll tenant engine state only, or allow browser to read MDS OHLC directly (auth complexity)?
4. **Testnet** — separate MDS instance mandatory.

---

## Related docs

| Doc | Relationship |
|-----|----------------|
| [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md) | Branch / deploy workflow |
| [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) | Single-bot ops (unchanged) |
| [`ALPHA_TRADERS_MANUAL.md`](ALPHA_TRADERS_MANUAL.md) | Operator tuning (unchanged) |
| [`TRADING_BOT_ALPHA_PHASE0.md`](TRADING_BOT_ALPHA_PHASE0.md) | Original Alpha scope / deferrals |

---

## Phase checklist (summary)

| Phase | Outcome |
|-------|---------|
| **0** | Spec + stale semantics + config design |
| **1** | MDS writes OHLC; tenant can opt in via flag |
| **2** | Shared TA/structure profiles on API |
| **3** | Hosted multi-tenant default |
| **4** | HA, streaming, production hardening |

*Last updated: 2026-06 — MDS not yet implemented; this document is the canonical dev path.*
