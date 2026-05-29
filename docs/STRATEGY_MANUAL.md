# XLedgerMate — Strategy Manual

*Version 1.3.4 · How the bot decides, not how to click buttons*

For startup, tabs, and wallet setup see [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md).

---

## What this bot is trying to do

XLedgerMate is a **defensive market maker** on XRP/RLUSD:

1. Post bid/ask offers around the live book mid.
2. Earn spread when both sides fill over time.
3. **Avoid adverse selection** — stepping back when price moves fast or edge is thin.
4. **Steer inventory** toward `inventory_target_xrp_ratio` (default 55% XRP) via quote skew, not on-chain swaps.

It is **not** a portfolio rebalancer. Moving from 80% → 55% XRP quickly requires **ask fills** or an **operator swap** on a DEX.

---

## Decision stack (each cycle)

Rough order of influence:

| Layer | What it does |
|--------|----------------|
| **Profile** (`safe`, `tight_spread`, `profit_mode`, …) | Base spread, size, skew strength, min edge |
| **Market condition** | Favorable / neutral / defensive / hostile — widens or tightens |
| **Inventory** | XRP-heavy → larger asks, smaller bids; RLUSD-heavy → opposite |
| **Mid momentum** | Fast rise → protect bids; fast fall → protect asks; **extreme (≥0.5%) can pause** a side |
| **Book pressure** | Bid-heavy or ask-heavy depth → widen/shrink vulnerable side |
| **Edge guards** | If L1 spread &lt; required edge → shrink size (not always widen) |
| **Spread validation** | Live orders must stay near touch; blocks placement if not |

When layers conflict, **protection usually beats inventory skew** (e.g. ask pause on extreme down momentum even when XRP-heavy).

---

## Session accounting (P&L)

| Metric | Meaning |
|--------|---------|
| **Portfolio (XRP equiv.)** | `XRP + RLUSD/mid` — same as cycle log `portfolio=` |
| **Session MTM P&L** | Current portfolio minus portfolio at **first cycle after engine start** (stored baseline) |
| **Balance Δ P&L** | Change in XRP/RLUSD balances only, marked at **current** mid — fees and fills, not mid revaluation |

Restarting the engine resets session baselines. Compare longer periods with `logs/portfolio_snapshots.csv`.

---

## Operating strategies (pick one)

1. **Defensive MM (default)** — Accept slow inventory drift; manual swap when deviation hurts.
2. **Inventory-first** — Swap toward ~55% XRP, then `safe` profile to maintain.
3. **Edge-first (`tight_spread`)** — Compete for spread; inventory may stay imbalanced.
4. **Hybrid** — Manual swap when &gt;15% off target; bot maintains between swaps.

---

## Profiles at a glance

| Profile | Skew strength | Typical use |
|---------|---------------|-------------|
| **safe** | Strong (1.45) | Capital-first, stronger inventory steer |
| **high_volatility** | Strong | Wide, small size in shocks |
| **thin_liquidity** | Strong | Thin books, book-pressure sensitive |
| **tight_spread** | Light (0.75) | Competitive when conditions are favorable |
| **profit_mode** | Moderate (0.90) | Calm, liquid, tight book only — tightest spreads, largest size, lowest edge floor |

---

## Key config levers

- `inventory_target_xrp_ratio` — Target XRP share (default 0.55).
- `order_sizes` — Per-level clip size; L1 only is common on pilot.
- `fund_with_xrp_only` — Bids off until RLUSD exists; keeps asks on when acquiring RLUSD.
- `active_profile` / auto profile switch — Risk posture.
- `min_edge_pct`, `dynamic_min_edge_enabled`, `edge_strictness` — When to shrink or skip.

---

## Further reading

- [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md) — GUI, mainnet gate, kill switch.
- [`MAINNET_PILOT.md`](MAINNET_PILOT.md) — Pilot branch scope.
- `strategy/quote_decision.py`, `strategy/market_microstructure.py` — Implementation detail.
