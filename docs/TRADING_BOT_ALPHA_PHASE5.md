# Trading Bot Alpha — Phase 5 Risk, Inventory, Reporting

**Version:** 1.0.0  
**Branch:** `alpha`

## What shipped

Phase 5 polishes supporting modules and completes end-to-end integration for the Phase 1 MVP goals.

| Area | Enhancements |
|------|----------------|
| `InventoryManager` | Real-time XRP/RLUSD allocation %, `buy_blocked_imbalance` / `sell_blocked_imbalance`, `cap_entry_size_xrp()` |
| `RiskEngine` | Session P&L tracker, auto kill-switch on drawdown breach, `validate_edge()` / `validate_entry()` / `validate_bracket_placement()` |
| `ReportingService` | Rich Telegram/console reports: portfolio %, brackets (fixed vs trailing), session P&L, alerts, last decision |
| `DecisionEngine` | Uses InventoryManager + RiskEngine for gates and sizing |
| `OrderManager` | Risk check before TP/SL placement |
| `EntryExecutor` | Risk re-validation before ledger writes |
| `AlphaApplication` | Graceful degradation, kill Telegram alert, rich `CycleReportContext` |

## Rich report sections

1. Mode / network / trading allowed
2. Portfolio balances with allocation %
3. Session P&L (XRP equiv MTM)
4. Inventory posture + imbalance blocks
5. Open brackets: pending / fixed TP-SL / trailing placeholder
6. Risk: kill switch, drawdown, preflight, alerts
7. Last decision + execution summary

## MVP goals met (Technical Specification)

| Goal | Status |
|------|--------|
| Limit orders only | Yes |
| Application-level bracket TP + SL + OCO | Yes |
| Liquidity-aware sizing | Yes |
| YAML config operator control | Yes |
| Telegram reporting | Rich cycle reports + kill alerts |
| dry_run default safe | Yes |
| Mainnet + kill switches + preflight | Yes |
| Preserve wallet/config hooks | Yes |

## CLI (unchanged)

```bash
python -m alpha status
python -m alpha run --once
python -m alpha run
```

## Phase 6 readiness

- **GUI** — wire to `CycleReportContext` / status cycle API
- **Advanced structure detection** — extend DecisionEngine (not MM port)
- **Production cutover** — systemd unit, VPS deploy script for `alpha` branch, soak testing
- **Trailing SL/TP** — replace `TRAILING_PLACEHOLDER` mode

## Tests

```bash
python -m pytest tests/test_alpha_*.py -q
```
