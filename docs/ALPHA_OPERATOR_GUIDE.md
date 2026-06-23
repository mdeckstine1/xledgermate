# xLedgerMate Trading Bot Alpha — Operator Guide

**Version:** 1.0.0 · **Branch:** `alpha`  
**Strategy:** Value accumulation (limit buys on weakness → bracket TP/SL)

This guide is for the **new Alpha bot**, not the legacy `ws-engine` market maker.

> **Going live?** Read **[`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md)** first — step-by-step HUD walkthrough, how orders are created (there is no manual Buy button), inventory requirements, and HOLD troubleshooting.

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
| `python main.py --mode alpha-hud` | **Operator HUD** (`:8765`, FastAPI — primary) |
| `python main.py --mode alpha-gui` | Streamlit lab panel (`:8503`, optional) |

**VPS access:** HUD binds to `hud_bind_host` (default public on VPS). Open `http://YOUR_VPS:8765` — **login required** when exposed publicly (see [HUD authentication](#hud-authentication)).

### HUD authentication

When `hud_bind_host` is `0.0.0.0` (public VPS), the Alpha HUD **requires** username + password (same as legacy WS HUD):

```yaml
# config/config.yaml — or use .env (recommended for secrets)
hud_auth_username: "operator"
hud_auth_password: "your-strong-password"
hud_auth_rp_id: "188.245.50.229"   # optional — WebAuthn / passkeys
```

Or in `.env` (gitignored):

```
XLG_HUD_USERNAME=operator
XLG_HUD_PASSWORD=your-strong-password
```

Auth auto-enables on public bind when credentials are set. Localhost-only bind (`127.0.0.1`) skips login unless `hud_auth_enabled: true`.

| Command | Purpose |
|---------|---------|
| `python main.py --mode alpha-run` | Same as `python -m alpha run` |
| `python scripts/alpha_validate.py` | Pre-cutover checks + tests |

Streamlit `:8503` is optional lab UI — use SSH tunnel if enabled.


## Key config parameters (conservative mainnet defaults)

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `dry_run` | `true` | **Must stay true for soak** |
| `trading_enabled` | `true` | Master switch (yaml) |
| `alpha_risk_per_trade_pct` | `0.5` | Max entry size as % of portfolio |
| `alpha_min_edge_threshold_pct` | `0.08` | Min edge vs mid for buy **and** sell |
| `alpha_buy_limit_offset_pct` | `0.15` | Limit buy % below mid |
| `alpha_sell_limit_offset_pct` | `0.15` | Limit sell % above mid |
| `alpha_max_pending_buys` | `1` | Max pending buy entries |
| `alpha_max_pending_sells` | `1` | Max strength-sell offers (non-bracket) |
| `alpha_max_inventory_imbalance_pct` | `0.10` | Block buys when too XRP-heavy |
| `initial_stop_loss_pct` | `0.015` | Bracket SL below entry |
| `take_profit_rr` | `2.0` | TP = 2× SL distance |
| `max_daily_drawdown_percent` | `10.0` | Kill switch threshold |

GUI **Pause** writes `logs/alpha_controls.json` without editing yaml.

### HUD operator API (Controls tab)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/operator/config` | Effective tunables + overrides + slider defaults |
| `PATCH` | `/operator/config` | Set runtime overrides (`logs/alpha_overrides.json`) |
| `POST` | `/operator/config/reload` | Queue yaml reload on next engine cycle |
| `POST` | `/operator/dry-run` | Toggle dry_run (`confirm`: `ENABLE_LIVE` / `ENABLE_DRY_RUN`) |
| `POST` | `/controls/pause` | Pause trading |
| `POST` | `/controls/resume` | Resume trading |
| `POST` | `/controls/kill` | Activate kill switch |
| `POST` | `/controls/clear-kill` | Clear kill switch |
| `POST` | `/controls/cancel-all` | Queue cancel all (`confirm`: `CANCEL_ALL`) |
| `POST` | `/brackets/{id}/adjust` | Queue SL/TP adjust (`leg`: `tp`/`sl`, `price`) |

Runtime overrides are applied each engine cycle; dangerous actions are queued in `logs/alpha_commands.json` and processed by `AlphaApplication`.

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
| `logs/alpha_overrides.json` | Runtime config overrides (HUD Controls tab) |
| `logs/alpha_commands.json` | Queued operator commands (cancel-all, reload, bracket adjust) |

---

## VPS (Cursor workflow)

1. Push `alpha` branch
2. SSH: `bash scripts/vps_deploy_alpha.sh`
3. HUD: `http://YOUR_VPS:8765` (or SSH tunnel if `hud_bind_host: 127.0.0.1`)
4. Optional Streamlit lab: `http://YOUR_VPS:8503`

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

- **[`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md)** — **start here for live trading & orders**
- [`PROJECT_INSTRUCTIONS.md`](../PROJECT_INSTRUCTIONS.md)
- [`ALPHA_MAINNET_CUTOVER.md`](ALPHA_MAINNET_CUTOVER.md)
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md)
- Phase docs: `docs/TRADING_BOT_ALPHA_PHASE*.md`
