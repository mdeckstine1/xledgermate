# Code audit report (quoting / config / runtime)

Audit date: 2026-06-03. Fixes applied in the same pass unless noted.

## Critical conflicts (fixed)

| Issue | Before | After |
|-------|--------|-------|
| **Dual touch resolvers** | `resolve_quoting_posture` (dead) + `resolve_dynamic_quoting_policy` | Removed legacy posture; tests use dynamic policy only |
| **Toxicity thresholds** | 0.15 / 0.18 / 0.20 / profile bounds scattered | `Profile.toxic_no_touch_ratio` + `toxic_pause_side_ratio`; shared `effective_toxic_ratio()` |
| **max_worse caps** | Engine hardcoded 8 bps poll refresh; validation always 50% | `core/quote_caps.effective_max_worse_than_touch_pct()` everywhere |
| **Book pressure doubled** | GUI preset 1.25 × profile 1.25 = 1.56× | Presets use config **1.0**; engine uses **profile** sensitivity only |
| **RuntimeState.load()** | 16 Tier-2 fields dropped on partial save | All persisted fields restored in `load()` |

## Dead config (removed)

- `competitive_near_touch_max_backoff_pct` — near-touch backoff is profile bounds in `dynamic_quoting_policy.py`
- `resolve_quoting_posture` / `QuotingPosture` — superseded by dynamic policy

## Retained but documented

- `inventory_hard_pause_deviation` — legacy; bailout uses `inventory_max_deviation` in all modes. GUI slider removed.
- `min_edge_pct` in YAML — migrated to `edge_strictness` on load only.

## Remaining intentional overlap

- **Fill quality sizing** (18% / 25% / 50%) vs **pause side** (`toxic_pause_side_ratio`) vs **refresh pause** (`toxic_refresh_pause_ratio`) — different actions; aligned to profile fields where possible.
- **Inventory skew**: label at 8%, cap at 8%, hard pause at 12% — distinct purposes (display / clip / pause).

## Operator notes

- **Toxic @30s 100%** with 1–2 fills is a small-sample artifact; see session notes in chat.
- Enable `dynamic_min_edge_enabled` on **safe** if you want book-based edge (GUI preset had it off).

## Follow-up (post v1.4.3 — see [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md))

| Item | Status |
|------|--------|
| Crossed book inflating portfolio / false drawdown | **Fixed** — `is_trustworthy_rlusd_mid`, last valid mid, session baseline guard |
| Phantom fill capture on bad mid | **Fixed** — trustworthy mid in `_log_fill` |
| Inverted BookOffers ask (~0.28) at RPC | **Open** — engine defends; root connector fix Tier 2.5 |
| Quotes when `market_edge_met` false | **Open** — edge-required gate Tier 2.5 |
| Gate 1 formal pass on mainnet | **Open** — use `safe`, balance PnL scoreboard |
