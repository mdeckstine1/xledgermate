# xLedgerMate — Operator Handover: Trading Bot Alpha

**Version:** 1.0.0  
**Branch:** `alpha`  
**VPS:** Cursor-managed (Hetzner)  
**Date:** Phase 8 complete

This document is the **single handover** for operators cutting over from legacy market-making (`ws-engine`) to Trading Bot Alpha.

---

## 1. What Trading Bot Alpha does

| Capability | Description |
|------------|-------------|
| Strategy | Value accumulation — limit buy on RLUSD-heavy weakness, sell on strength |
| Orders | Limit orders only |
| Brackets | After buy fill: TP + SL limit sells; OCO cancels opposing leg |
| Sizing | Liquidity depth, portfolio %, risk-per-trade caps |
| Safety | `dry_run` default, kill switch, drawdown, preflight, operator pause |
| Reporting | Telegram rich reports, GUI, `logs/alpha_activity.jsonl` |
| Config | Same `config/config.yaml` + `credentials.local.yaml` hooks |

**Not included (post-MVP):** live SL/TP trail price updates, full HTF charting, legacy MM quoting.

---

## 2. VPS cutover — step by step

### Prerequisites

- SSH access: `ssh -i ~/.ssh/hetzner_xledgermate root@188.245.50.229`
- `alpha` branch pushed to origin
- `config/config.yaml` + `credentials.local.yaml` on VPS (unchanged paths)
- RLUSD trust line on mainnet

### Automated cutover (recommended)

```bash
cd /root/xledgermate
bash scripts/alpha_cutover_vps.sh
```

This script:
1. Backs up legacy state → `backups/pre-alpha-cutover-<timestamp>/`
2. Stops `xledgermate` + `xledgermate-ws-hud`
3. Checks out `alpha`, installs deps
4. Forces `dry_run: true` for soak
5. Installs/enables `xledgermate-alpha` systemd unit
6. Runs `alpha_validate.py` and starts Alpha

**Optional:** cancel open offers before cutover:
```bash
CANCEL_OFFERS=1 bash scripts/alpha_cutover_vps.sh
```

### Manual cutover (if you prefer)

| Step | Command |
|------|---------|
| 1. Backup | `bash scripts/alpha_backup_legacy.sh` |
| 2. Stop legacy | `systemctl stop xledgermate xledgermate-ws-hud` |
| 3. Cancel offers (optional) | `python main.py --mode cancel-offers` |
| 4. Checkout Alpha | `git checkout alpha && git pull` |
| 5. Validate | `python scripts/alpha_validate.py` |
| 6. Ensure dry_run | `dry_run: true` in config |
| 7. Install systemd | `cp scripts/systemd/xledgermate-alpha*.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable xledgermate-alpha` |
| 8. Start | `systemctl start xledgermate-alpha` |
| 9. Verify | `python -m alpha status` |

### GUI access (SSH tunnel)

```powershell
ssh -i ~/.ssh/hetzner_xledgermate -L 8503:127.0.0.1:8503 root@188.245.50.229
```

Browser: http://localhost:8503

Enable GUI service (optional):
```bash
systemctl enable --now xledgermate-alpha-gui
```

---

## 3. Dry-run soak (mandatory before live)

Run **24–48 hours** on mainnet with `dry_run: true`:

```bash
# Already running via systemd, or:
python -m alpha run --max-cycles 200
```

**Check daily:**
- [ ] `logs/alpha_activity.jsonl` — cycles complete, no repeated errors
- [ ] `python -m alpha status` — preflight OK
- [ ] GUI — inventory %, session P&L reasonable
- [ ] Telegram — reports arrive (if enabled)
- [ ] No `entry_buy_placed` in logs (dry-run should log `entry_execute_dry_run` only)

---

## 4. Go-live — flip `dry_run` to false

### Final validation checklist

- [ ] `python scripts/alpha_validate.py` — all tests pass
- [ ] Soak complete (24–48h dry-run)
- [ ] `logs/kill_switch.json` — `"active": false`
- [ ] `logs/alpha_controls.json` — not paused (or absent)
- [ ] Legacy `ws-engine` **stopped** and disabled
- [ ] Operator understands rollback procedure
- [ ] Telegram kill alerts tested

### Recommended conservative mainnet config

```yaml
# Safety
dry_run: false              # ONLY after checklist above
testnet: false
trading_enabled: true

# Alpha entry (conservative)
alpha_risk_per_trade_pct: 0.5
alpha_max_pending_buys: 1
alpha_min_edge_threshold_pct: 0.08
alpha_buy_limit_offset_pct: 0.15
alpha_max_inventory_imbalance_pct: 0.10
alpha_cycle_interval_seconds: 60
alpha_base_order_size_xrp: 50.0

# Brackets
initial_stop_loss_pct: 0.015
take_profit_rr: 2.0
partial_fill_mode: wait_full
min_fill_size_xrp_for_oco: 0.5
bracket_trailing_enabled: false

# Risk
max_daily_drawdown_percent: 10.0
inventory_target_xrp_ratio: 0.55
xrp_reserve: 12.0
min_order_size_xrp: 1.0

# Telegram (recommended live)
telegram_enabled: true
telegram_kill_alerts_enabled: true
```

### Go-live commands

```bash
# Edit config
nano config/config.yaml   # dry_run: false

# Restart
systemctl restart xledgermate-alpha

# Watch first 3 cycles
tail -f logs/alpha_activity.jsonl
python -m alpha status
```

---

## 5. Monitoring & maintenance

### What to watch

| Signal | Where | Action if bad |
|--------|-------|----------------|
| Kill switch | GUI, `logs/kill_switch.json`, Telegram | Pause, investigate drawdown |
| Drawdown | GUI / status report | Review inventory; may auto-kill |
| Session P&L | GUI, status report | Compare to expectation |
| Brackets | GUI, `logs/alpha_brackets.json` | Stuck pending → check ledger offers |
| RPC errors | `logs/alpha_activity.jsonl` | Increase `alpha_cycle_interval_seconds` |
| Preflight failures | status / Telegram | Trust line, balances, mid price |

### Daily operator routine

1. `python -m alpha status` (or Telegram morning report)
2. Glance GUI — allocation %, open brackets
3. Confirm `dry_run` matches intent
4. Weekly: `python scripts/alpha_validate.py`

### Log files

| File | Purpose |
|------|---------|
| `logs/alpha_activity.jsonl` | Cycle audit trail |
| `logs/alpha_brackets.json` | Bracket persistence |
| `logs/alpha_session.json` | Session P&L baseline |
| `logs/kill_switch.json` | Kill state |
| `logs/alpha_controls.json` | GUI pause |

### Deploy updates (Cursor workflow)

```bash
# Local: commit + push alpha branch
# VPS:
cd /root/xledgermate
bash scripts/vps_deploy_alpha.sh
```

---

## 6. Rollback plan

### Quick rollback (emergency)

```bash
# 1. Pause / dry-run immediately
sed -i 's/^dry_run: false/dry_run: true/' config/config.yaml
systemctl restart xledgermate-alpha

# 2. Or full legacy restore
bash scripts/alpha_rollback_to_legacy.sh
```

`alpha_rollback_to_legacy.sh`:
- Stops Alpha services
- Sets `dry_run: true`
- Checks out `Ashigaru-Shoshin`
- Restarts legacy `xledgermate` + HUD

### Cancel open offers

```bash
python main.py --mode cancel-offers
```

### Restore config from backup

```bash
cp backups/pre-alpha-cutover-*/config.yaml config/config.yaml
```

---

## 7. Legacy MM sunset

Legacy `ws-engine` market making is **deprecated** for new production on this Bot Account.

| Item | Status |
|------|--------|
| `Ashigaru-Shoshin` branch | Archived for MM reference / rollback |
| `python main.py --mode ws-engine` | Do not run alongside Alpha live |
| HUD `:8765` | Legacy MM operator surface — optional read-only |
| `gui/streamlit_gui.py` | Lab / legacy — not Alpha |

See [`LEGACY_MM_SUNSET.md`](LEGACY_MM_SUNSET.md) for archive guidance.

**Primary bot:** branch `alpha`, command `python -m alpha run`, systemd `xledgermate-alpha`.

---

## 8. Remaining open items (future)

| Item | Priority |
|------|----------|
| Live SL/TP trail price updates | Medium |
| Proportional bracket resize after BRACKET_ACTIVE | Low |
| Cancelled-buy vs fill disambiguation | Medium |
| Hourly Telegram digest automation | Low |
| Full HTF structure detection | Low |

None block cautious live trading with conservative sizing.

---

## 9. Quick reference card

```bash
# Status
python -m alpha status

# Validate
python scripts/alpha_validate.py

# Cutover
bash scripts/alpha_cutover_vps.sh

# Deploy update
bash scripts/vps_deploy_alpha.sh

# Rollback
bash scripts/alpha_rollback_to_legacy.sh

# GUI (local tunnel)
python main.py --mode alpha-gui
```

---

## 10. Sign-off

| Checkpoint | Operator | Date |
|------------|----------|------|
| Backup completed | | |
| Legacy stopped | | |
| Alpha dry-run soak (24–48h) | | |
| Validation passed | | |
| Go-live approved (`dry_run: false`) | | |
| Rollback tested (dry-run) | | |

**Trading Bot Alpha — handover complete. Safe trading.**
