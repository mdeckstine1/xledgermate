# xLedgerMate Trading Bot Alpha — Operator Guide

**Version:** 1.0.0 · **Branch:** `alpha`  
**Strategy:** Value accumulation (limit buys on weakness → bracket TP/SL)

This guide is for the **new Alpha bot**, not the legacy `ws-engine` market maker.

---

## What Alpha does

1. Monitors XRP/RLUSD inventory vs target ratio
2. Places **limit buy** below mid when RLUSD-heavy and edge/depth allow
3. On fill, places **TP + SL** limit sells (application-level OCO)
4. Cancels opposing leg when TP or SL fills
5. Respects **dry_run**, kill switch, drawdown, and operator pause

---

## Setup

### 1. Config files

| File | Purpose |
|------|---------|
| `config/config.yaml` | Operator settings (gitignored) |
| `config/credentials.local.yaml` | Secret key sidecar (optional, wins over yaml) |
| `config/config.example.yaml` | Template — copy to `config.yaml` |

```powershell
copy config\config.example.yaml config\config.yaml
```

Required:
- `bot_account_address` — your Bot Account on XRPL
- Secret via `credentials.local.yaml` or `bot_secret_key` (never commit)
- `testnet: false` for mainnet
- `dry_run: true` until soak complete

### 2. Mainnet RLUSD trust line

Issuer (mainnet): `rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De`

```powershell
python main.py --mode setup-trust
```

### 3. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Running Alpha

| Command | Purpose |
|---------|---------|
| `python -m alpha status` | One read-only snapshot (+ optional Telegram) |
| `python -m alpha run --once` | Single trading cycle |
| `python -m alpha run` | Continuous loop |
| `python -m alpha run --max-cycles 50` | Soak test |
| `python main.py --mode alpha-gui` | Streamlit GUI (`:8503`) |
| `python main.py --mode alpha-run` | Same as `python -m alpha run` |
| `python scripts/alpha_validate.py` | Pre-cutover checks + tests |

---

## Key config parameters (conservative mainnet defaults)

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `dry_run` | `true` | **Must stay true for soak** |
| `trading_enabled` | `true` | Master switch (yaml) |
| `alpha_risk_per_trade_pct` | `0.5` | Max entry size as % of portfolio |
| `alpha_min_edge_threshold_pct` | `0.08` | Min edge vs mid to buy |
| `alpha_buy_limit_offset_pct` | `0.15` | Limit buy % below mid |
| `alpha_max_pending_buys` | `1` | One entry at a time |
| `alpha_max_inventory_imbalance_pct` | `0.10` | Block buys when too XRP-heavy |
| `initial_stop_loss_pct` | `0.015` | Bracket SL below entry |
| `take_profit_rr` | `2.0` | TP = 2× SL distance |
| `max_daily_drawdown_percent` | `10.0` | Kill switch threshold |

GUI **Pause** writes `logs/alpha_controls.json` without editing yaml.

---

## Flipping dry_run to live

1. Complete soak on **mainnet** with `dry_run: true` (see cutover checklist)
2. Run `python scripts/alpha_validate.py`
3. Confirm kill switch clear: GUI or `logs/kill_switch.json`
4. Edit `config/config.yaml`: `dry_run: false`
5. Restart: `systemctl restart xledgermate-alpha` (VPS) or re-run CLI
6. Watch first 3 cycles in GUI + Telegram
7. **Rollback:** set `dry_run: true`, restart, cancel offers if needed

---

## Logs (operator)

| Path | Content |
|------|---------|
| `logs/alpha_activity.jsonl` | Cycle decisions, executions |
| `logs/alpha_brackets.json` | Bracket state persistence |
| `logs/alpha_session.json` | Session P&L baseline |
| `logs/kill_switch.json` | Kill switch state |
| `logs/alpha_controls.json` | GUI pause/resume |

---

## VPS (Cursor workflow)

1. Push `alpha` branch
2. SSH: `bash scripts/vps_deploy_alpha.sh`
3. GUI tunnel: `ssh -L 8503:127.0.0.1:8503 -i ~/.ssh/hetzner_xledgermate root@YOUR_VPS`
4. Open http://localhost:8503

**Switch from legacy MM to Alpha:** see [`ALPHA_MAINNET_CUTOVER.md`](ALPHA_MAINNET_CUTOVER.md)

**Rollback to legacy MM:** `bash scripts/alpha_rollback_to_legacy.sh`

---

## Safety rules

- Never commit secrets
- Default `dry_run: true`
- Start with small `alpha_risk_per_trade_pct`
- Use kill switch + operator pause when uncertain
- Alpha and legacy `ws-engine` are **separate** — do not run both live without intent

---

## Further reading

- [`PROJECT_INSTRUCTIONS.md`](../PROJECT_INSTRUCTIONS.md)
- [`ALPHA_MAINNET_CUTOVER.md`](ALPHA_MAINNET_CUTOVER.md)
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md)
- Phase docs: `docs/TRADING_BOT_ALPHA_PHASE*.md`
