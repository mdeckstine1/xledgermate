# xLedgerMate Trading Bot Alpha — Operator Guide

**Version:** 1.0.1 · **Branch:** `alpha` · **Release:** `samurai-v1.0.1`  
**Strategy:** Aggressive Bag Growth (TA-Driven & HUD-Controlled — limit buys on dips → bracket TP/SL → patient re-entry)

This guide is for the **new Alpha bot**, not the legacy `ws-engine` market maker.

> **Going live?** Read **[`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md)** first — step-by-step HUD walkthrough, how orders are created (there is no manual Buy button), inventory requirements, and HOLD troubleshooting.

> **Want the trader's voice?** **[`ALPHA_TRADERS_MANUAL.md`](ALPHA_TRADERS_MANUAL.md)** — HUD guide by tab/card (Bull/Neutral/Bear per card) + **Appendices A–W**.

> **Hands-off soak?** **[48-hour watch checklist](ALPHA_TRADERS_MANUAL.md#48-hour-watch-checklist-hands-off-soak)** in the traders manual — baseline snapshot (2026-06-24) and compare table for ~2026-06-26.

---

## What Alpha does

1. Targets **~75% XRP** allocation (Aggressive Bag Growth — minimize idle RLUSD)
2. Places **limit buy** below mid when RLUSD-heavy, edge/depth/TA allow
3. On fill, places **TP + SL** limit sells (application-level OCO)
4. After **TP or SL** exit, **re-entry gate** waits for dip/stabilization + TA before next buy
5. Places **limit sell** on XRP strength (profit take / rebalance)
6. Respects **dry_run**, kill switch, drawdown, and operator pause

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
| `inventory_target_xrp_ratio` | `0.75` | XRP bag target (Aggressive Bag Growth) |
| `alpha_weakness_deviation` | `0.02` | Buy when this far below XRP target |
| `alpha_strength_deviation` | `0.04` | Strength sell threshold |
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

### HUD-tunable strategy keys (Aggressive Bag Growth)

| Key | Default | HUD panel |
|-----|---------|-----------|
| `inventory_target_xrp_ratio` | 0.75 | Risk & entry |
| `alpha_ta_weight` | 1.0 | TA |
| `alpha_reentry_tp_cooldown_cycles` | 4 | Re-entry |
| `alpha_reentry_tp_cooldown_minutes` | 0 | Re-entry |
| `alpha_reentry_sl_cooldown_cycles` | 10 | Re-entry |
| `alpha_reentry_sl_cooldown_minutes` | 0 | Re-entry |
| `alpha_reentry_tp_min_ta_score` | 1.5 | Re-entry |
| `alpha_reentry_sl_min_ta_score` | 2.5 | Re-entry |
| `alpha_reentry_scratch_sl_max_loss_pct` | 0.15 | Re-entry → SL mitigations |
| `alpha_reentry_scratch_sl_cooldown_cycles` | 4 | Re-entry → SL mitigations |
| `alpha_reentry_sl_cluster_window_seconds` | 1800 | Re-entry → SL mitigations |
| `alpha_reentry_recovery_enabled` | true | Re-entry → SL mitigations |
| `alpha_reentry_recovery_release_pct` | 0.05 | Re-entry → SL mitigations |
| `alpha_reentry_recovery_min_cycles` | 2 | Re-entry → SL mitigations |
| `alpha_reentry_post_clear_buy_spacing_cycles` | 5 | Re-entry → SL mitigations |

Legacy YAML keys `alpha_reentry_tp_min_cycles` / `alpha_reentry_sl_min_cycles` migrate automatically to `*_cooldown_cycles` on load.

Re-entry cooldown reasons in logs and Decision: `post_tp_cooldown`, `post_sl_cooldown` (may include `tier=scratch`), `reentry_reload_spacing`, `recovery_early_release`.

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
| `logs/operator_deposits.json` | Operator inbound funding (bag growth adjustment) |
| `logs/kill_switch.json` | Kill switch state |
| `logs/alpha_controls.json` | GUI pause/resume |
| `logs/alpha_overrides.json` | Runtime config overrides (HUD Controls tab) |
| `logs/alpha_reentry.json` | Persisted re-entry gate (cooldown, sl_tier, spacing) |
| `logs/alpha_market.db` | Per-cycle market metrics (ATR%, vol, regime) |
| `logs/alpha_commands.json` | Queued operator commands (cancel-all, reload, bracket adjust) |
| `logs/alpha_defensive_circuit.json` | Auto-defensive circuit state (PRO tab) |
| `logs/alpha_treasury.json` | Treasury placeholder notes (PRO tab — not wired) |

---

## PRO (Replay + defensive circuit)

The HUD **PRO** tab (nav: **Live → … → Activity → PRO → SKYNET → Config**) surfaces:

| Block | Purpose |
|-------|---------|
| **Alpha Replay** | Rolling TP/SL ratio, realized P&amp;L, scratch-SL churn, verdict (`healthy` / `sl_heavy` / `bleeding` / `churn`) from `logs/trades_*.csv` + bracket store |
| **Auto-defensive circuit** | Engine auto-trips on bad replay metrics; applies bear regime + tighter caps via `logs/alpha_overrides.json` |
| **Treasury** | Placeholder only — sideline Tangem tranche deploy not implemented |

**Defensive bundle when tripped:** `alpha_operator_market_regime=bear`, `alpha_max_pending_buys≤1`, wider `alpha_buy_limit_offset_pct`, longer `alpha_reentry_sl_cooldown_cycles`, lower `alpha_risk_per_trade_pct`. **Pause** and **kill switch** always override. Use **Release defensive** on PRO to restore pre-trip overrides.

Config keys (`config.yaml`):

```yaml
alpha_defensive_circuit_enabled: true
alpha_defensive_window_hours: 14.0
alpha_defensive_sl_exit_threshold: 8
alpha_defensive_realized_loss_xrp: 3.0
alpha_defensive_min_exits: 4
alpha_defensive_auto_release_hours: 6.0
```

Traders manual: **[Appendix W — SL-heavy night / defensive circuit](ALPHA_TRADERS_MANUAL.md#appendix-w--sl-heavy-night-defensive-circuit-pro)**.

---

## SKYNET (Ask + Agent Smith)

The HUD **SKYNET** tab provides AI-powered knob suggestions (**Ask SKYNET**), bounded **Agent Smith** (Phase 2), and optional **Full SKYNET** autonomy (Phase 3). **Operator phase** (`trust` | `scale` | `aggressive`) and **market regime** (`bull` | `neutral` | `bear`) bias every SKYNET cycle — set them before asking for strategy advice.

| Phase | Purpose |
|-------|---------|
| **trust** | Patient soak; anti-bleed; default |
| **scale** | Modest accumulation after clean nights |
| **aggressive** | Bag-growth push within guardrails |

Full guide: **[Tuning SKYNET](ALPHA_TRADERS_MANUAL.md#tuning-skynet-ask-agent-smith-full-mode)** and **Appendices S–U** in the traders manual. Requires an xAI API key in `.env` (`XAI_API_KEY`). Inference uses Grok-family models on xAI's backend; prompts and guardrails are SKYNET-owned.

---

## Bag growth vs trading edge

The sidebar **Bag growth** block answers: *“Is my stack bigger?”* vs *“Is the bot winning trades?”*

| Metric | Meaning |
|--------|---------|
| **Since baseline** | Portfolio (XRP + RLUSD at mid) vs `logs/alpha_session.json` anchor — includes price moves and RLUSD→XRP deployment |
| **Bot-adjusted growth** | Since baseline minus operator deposits (`logs/operator_deposits.json`) — record inbound funding on **Config** tab |
| **This week** | Same portfolio measure since Monday 00:00 UTC (`logs/alpha_bag_week.json`) |
| **Trading edge 7d** | Sum of realized bracket P&L from tax CSV (TP/SL only) — true trading bleed/win |
| **Session P&L** | Mark-to-market since baseline — can diverge from bag growth and from realized |

**Telegram:** Hourly digest includes a compact bag-growth line. Weekly report (`scripts/weekly_telegram_report.py`) sends a fuller rollup every **Monday 09:00 UTC** when `telegram_weekly_report_enabled: true`. Install timer: `bash scripts/install_weekly_telegram_timer.sh`.

---

## Walk-away preset

SKYNET tab → **Walk-away preset** (or `POST /operator/walkaway`) applies:

- **Operator phase:** `trust` — patient entries, anti-churn
- **Knobs:** e.g. buy offset 0.18, max pending 2, higher min sell score, longer SL cooldown
- **Agent Smith:** ON with default guardrails
- **Full SKYNET:** stays OFF (no auto-apply without explicit `ENABLE_FULL_SKYNET`)

Use when you want hands-off monitoring without aggressive churn or full autonomy.

**Bracket edge cleanup** (SKYNET tab → **Bracket edge cleanup** or `POST /operator/bracket-edge-cleanup`) applies anti-churn knobs when realized TP/SL is SL-heavy / zero TP:

- **Trust phase**, `max_pending_buys` 1, higher `min_buy` TA, patient buy offset
- **Closer TP** (~2.5%) and **SL** (~2.5%), RR 1.5, deferred SL buffer
- Longer re-entry after SL — does **not** enable Agent Smith or full SKYNET

Pair with **Walk-away** if you also want Agent Smith ON. Use SKYNET quick button **Bracket edge — 48h watch** after applying.

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
- **[`ALPHA_TRADERS_MANUAL.md`](ALPHA_TRADERS_MANUAL.md)** — **Part 1:** HUD by tab/card · **Part 2:** funding, coupling, soak · **Appendices A–W**
- [`PROJECT_INSTRUCTIONS.md`](../PROJECT_INSTRUCTIONS.md)
- [`ALPHA_MAINNET_CUTOVER.md`](ALPHA_MAINNET_CUTOVER.md)
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md)
- Phase docs: `docs/TRADING_BOT_ALPHA_PHASE*.md`
