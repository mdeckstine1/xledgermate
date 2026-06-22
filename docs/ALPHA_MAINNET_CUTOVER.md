# xLedgerMate Alpha — Mainnet Cutover Checklist

Use this checklist before setting `dry_run: false` on mainnet.

## Switching from legacy MM (`ws-engine`) to Alpha

Alpha and legacy market making **must not run live simultaneously** on the same Bot Account.

### Recommended migration (VPS)

1. **Stop legacy engine**
   ```bash
   systemctl stop xledgermate
   systemctl stop xledgermate-ws-hud   # optional — HUD is legacy MM
   ```

2. **Optional: cancel legacy offers**
   ```bash
   cd /root/xledgermate
   # On legacy branch if needed:
   .venv/bin/python main.py --mode cancel-offers
   ```

3. **Deploy Alpha branch**
   ```bash
   bash scripts/vps_deploy_alpha.sh
   ```

4. **Install systemd units** (first time only)
   ```bash
   cp scripts/systemd/xledgermate-alpha.service /etc/systemd/system/
   cp scripts/systemd/xledgermate-alpha-gui.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable xledgermate-alpha
   ```

5. **Verify config** — same `config/config.yaml` and `credentials.local.yaml` work for Alpha
   - `testnet: false`
   - `dry_run: true` for soak

6. **Soak Alpha** before live (see below)

### Rollback to legacy MM

```bash
bash scripts/alpha_rollback_to_legacy.sh
```

This stops Alpha, forces `dry_run: true`, checks out `Ashigaru-Shoshin`, restarts `ws-engine` + HUD.

---

## Pre-flight (local or VPS)

- [ ] On branch `alpha`, latest code deployed (`scripts/vps_deploy_alpha.sh`)
- [ ] `python scripts/alpha_validate.py` passes
- [ ] `config/config.yaml`: `testnet: false`, `dry_run: true` initially
- [ ] `config/credentials.local.yaml`: bot secret present (never commit)
- [ ] `bot_account_address` matches secret
- [ ] RLUSD trust line to mainnet issuer `rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De`
- [ ] `python -m alpha status` — preflight OK, sensible balances
- [ ] Legacy `ws-engine` stopped if switching bots

## Soak (dry-run mainnet)

- [ ] `python -m alpha run --max-cycles 50` or systemd with `dry_run: true`
- [ ] Review `logs/alpha_activity.jsonl` — decisions logged, no unexpected errors
- [ ] GUI (`python main.py --mode alpha-gui`) — inventory %, brackets, P&L look sane
- [ ] Telegram configured — receive cycle/kill alerts
- [ ] Conservative sizing: `alpha_risk_per_trade_pct: 0.5`, `alpha_max_pending_buys: 1`
- [ ] Test operator pause/resume and kill switch clear in GUI

## Manual dry-run checklist (small capital)

- [ ] Run during active market hours; observe 10+ cycles
- [ ] Confirm `entry_execute_dry_run` in logs when `dry_run: true` (no ledger writes)
- [ ] Verify decisions match inventory posture (buy when RLUSD-heavy, etc.)
- [ ] Note RPC latency; if errors spike, increase `alpha_cycle_interval_seconds`

## Live cutover

- [ ] Operator confirms kill switch clear: `logs/kill_switch.json` inactive
- [ ] Operator pause off: `logs/alpha_controls.json` → `trading_paused: false`
- [ ] Set `dry_run: false` in `config/config.yaml`
- [ ] Restart: `systemctl restart xledgermate-alpha`
- [ ] Watch first 3 cycles in GUI + Telegram
- [ ] Confirm real offers only when edge + inventory + risk gates pass
- [ ] Keep `alpha_max_pending_buys: 1` for first live session

## Rollback (emergency)

- [ ] Set `dry_run: true` in config and `systemctl restart xledgermate-alpha`
- [ ] GUI → Clear kill switch or pause trading
- [ ] Cancel open offers: `python main.py --mode cancel-offers`
- [ ] Full legacy rollback: `bash scripts/alpha_rollback_to_legacy.sh`

## Cursor / VPS workflow

1. Develop on `alpha` branch locally
2. Push to origin
3. SSH VPS → `bash scripts/vps_deploy_alpha.sh`
4. Validate → `python scripts/alpha_validate.py`
5. Tunnel GUI: `ssh -L 8503:127.0.0.1:8503 -i ~/.ssh/hetzner_xledgermate root@188.245.50.229`
6. Monitor `logs/alpha_activity.jsonl` and Telegram

## Recommended starting parameters

See [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) and [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md).

## Post-MVP (not blocking go-live)

- Full HTF structure / ML detection
- Live SL/TP trail price updates (mode flag exists today)
- Hourly Telegram digest automation
