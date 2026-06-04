# Mainnet pilot

**Branch:** `tier-2-polish` (successor to `mainnet-pilot`)  
**Version:** **1.4.3+**  
**Capital:** ~**247 XRP** total bot wallet (liquid XRP + RLUSD + reserve) — not the 11,254 XRP config placeholder.

**Goal:** Validate **safe** market making on mainnet (Gate 1), then competitive **`tight_spread`** (Gate 2), then scale (Gate 3). Long-term: **grow holdings** via positive **balance PnL**, not inflated MTM on bad books.

## Scope (current)

- `testnet: false`, `dry_run: false` when operator-ready
- Profile **`safe`** until Gate 1 passes — L1 **10–15 XRP**, L2/L3 **0**
- Spread check must pass each cycle (engine blocks live placement if not)
- Risk capital synced to **live portfolio** in GUI
- Kill stack: drawdown (honest mids), spread failures, optional session balance loss (**−0.35 XRP / 25 fills**), toxic kill **off** by default
- Monitor: Dashboard, `logs/trades_YYYY-MM.csv`, `logs/portfolio_snapshots.csv`, `logs/decisions.jsonl`

## Scripts

```powershell
python scripts/weekly_skim_report.py
python scripts/analyze_session.py
python scripts/portfolio_bleed_analysis.py
```

## Out of scope (until Gate 2+)

- **`tight_spread` / `profit_mode`** as default money mode
- Scaling toward **~11k XRP** narrative capital
- Unattended 24/7 without monitoring
- ML / auto-learning

## Operator checklist

1. **Mainnet go-live gate** — [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md)  
2. **Field gates (Gate 1 → 2 → 3)** — [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)
