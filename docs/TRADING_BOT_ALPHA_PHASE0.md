# Trading Bot Alpha — Phase 0 Audit

**Date:** 2026-06-21  
**Source branch:** `Ashigaru-Shoshin` @ `d557f92` (v2.3.2)  
**New branch:** `alpha` (pushed to `origin/alpha`)  
**Scope:** Evaluation and transition plan only — **no Phase 1 implementation in this document.**

---

## Executive summary

Trading Bot Alpha should fork from the current **WS pure A-S production path** (`python main.py --mode ws-engine`), not the deprecated HTTP-poll legacy engine. The Ashigaru-Shoshin stack already provides:

- A single **`dry_run` boolean** in YAML that gates all live XRPL submit/cancel paths in `ws_pure_engine.py`
- **Mainnet-ready** issuer resolution and trustline tooling
- **Credential isolation** via `config/credentials.local.yaml` with unchanged load semantics
- Layered quote decision (L1–L5), inventory limits, drawdown kill, and structured logging

Phase 0 recommendation: **reuse the config + connector + ws-engine + risk core**; **trim** lab HUD, Grok intel, soak reports, and legacy `engine/trading_engine.py` over subsequent phases.

---

## Branch confirmation

| Item | Value |
|------|--------|
| Branch name | `alpha` |
| Created from | `Ashigaru-Shoshin` (`d557f92`) |
| Remote | `origin/alpha` (tracking set) |
| VPS deploy script | `scripts/vps_deploy_ashigaru.sh` — update branch name when Alpha VPS is provisioned |

```bash
git checkout alpha
git log -1 --oneline   # d557f92 Release v2.3.2: ...
```

---

## Critical preservation requirements

### 1. Secret key and wallet loading — **KEEP AS-IS**

| Component | Path | Behavior |
|-----------|------|----------|
| Config dataclass | `config/settings.py` | `BotConfig` fields `bot_account_address`, `bot_secret_key` |
| Config file path | `config/settings.py` → `CONFIG_FILE` | **`config/config.yaml`** (resolved as `Path(__file__).parent / "config.yaml"`) |
| Credentials sidecar | `config/credentials.local.yaml` | Gitignored; **wins** over `config.yaml` for both credential fields |
| Merge on load | `_merge_credentials_into_config()` | Order: sidecar → main yaml → `.bak` |
| Save hook | `_write_credentials_sidecar()` | Secrets written to sidecar only; general saves use `patch_config_file()` which **skips** credential keys |
| Wallet derivation | `utils/wallet_credentials.py` | `wallet_from_bot_secret()` — family `sEd*` / Xaman `sn...` |
| XRPL connector | `connectors/xrpl_connector.py` | `load_wallet()` — derived address must match `bot_account_address` |
| WS engine wiring | `experimental/ws_feed/ws_pure_engine.py` | `_build_connector()` passes `config.bot_secret_key`; reloads `BotConfig.load()` each cycle |
| CLI trust/send | `main.py` | `setup-trust`, `trust-no-ripple`, `send` require address + secret |

**Alpha rule:** Do not change `CONFIG_FILE`, sidecar name, merge order, or `patch_config_file` credential exclusion. New Alpha code must call `BotConfig.load()` — never hardcode paths or duplicate secret loading.

**Tests to keep green:** `tests/test_config_credentials.py`

---

### 2. YAML config location and loading pattern — **KEEP AS-IS**

| Operation | API | Notes |
|-----------|-----|-------|
| Load | `BotConfig.load()` | Defaults + YAML merge + credential merge + corrupt-file fallback |
| Full save | `BotConfig.save()` | Writes yaml + sidecar + `.bak` |
| Partial patch | `patch_config_file(updates)` | HUD Telegram, non-secret toggles; never touches credentials |
| Template | `config/config.example.yaml` | Git-tracked reference |

**Alpha rule:** All new Alpha settings extend `BotConfig` in `config/settings.py` and `config.example.yaml`. Do **not** relocate config to `.env` for trading parameters (`.env` remains for Grok/HUD login only per `utils/env_secrets.py`).

---

### 3. Dry-run vs live trading — **ALREADY CLEAN; PRESERVE SINGLE SWITCH**

**Config field:** `dry_run: bool` (default `True` in `BotConfig`)

**Enforcement (production path):** `experimental/ws_feed/ws_pure_engine.py`

| `dry_run` | Effect |
|-----------|--------|
| `true` | Full quote pipeline runs; reads mainnet book/balances; **no** `_sync_offers` submit/cancel; summary says “Dry-run: would sync …” |
| `false` | Live `plan_order_sync` + XRPL submit when `trading_enabled` and secret present |

Additional gates for live: `utils/preflight.py` (trust line, secret, balances), `trading_enabled`, kill switch.

**Alpha Phase 0 mainnet paper config:**

```yaml
testnet: false
dry_run: true
trading_enabled: true
```

**Go live (later):** Set `dry_run: false` only after `setup-trust` + preflight pass. No code change required.

**Do not confuse with:**
- `scripts/hourly_telegram_report.py --dry-run` (Telegram preview only)
- `experimental/ws_feed/pure_dry_run_executor.py` (lab tester virtual ledger — **not** production `dry_run`)

---

### 4. Mainnet, address, and RLUSD trustline — **NO NEW WALLET**

| Setting | Mainnet value |
|---------|----------------|
| `testnet` | `false` |
| `resolved_rlusd_issuer()` | `rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De` (unless `rlusd_issuer` override) |
| Trustline CLI | `python main.py --mode setup-trust` / `trust-no-ripple` |
| Send RLUSD out | `python main.py --mode send --asset RLUSD --amount N --to r...` |

Existing bot address and on-ledger trustline on Ashigaru VPS carry forward unchanged.

---

## Subsystem audit

### Telegram

| Piece | Path | Alpha recommendation |
|-------|------|----------------------|
| Config keys | `settings.py`: `telegram_*`, quiet hours, hourly/kill flags | **Reuse** — same yaml fields |
| Alerts | `monitoring/telegram_alerts.py` | **Reuse** for kill-switch alerts |
| Hourly report | `scripts/hourly_telegram_report.py` | **Optional** — defer or slim for Alpha |
| HUD patch | `experimental/ws_feed/hud_telegram_support.py` | **Defer** if HUD trimmed |
| Systemd timer | `scripts/ensure_hourly_telegram_timer.sh` | **Optional** ops |

Secrets: `telegram_token` + `telegram_chat_id` live in `config/config.yaml` only (not sidecar).

---

### Risk, inventory, and kill switch

| Module | Path | Role |
|--------|------|------|
| Inventory limits | `risk/inventory_limits.py` | Pause vulnerable side past `inventory_max_deviation` |
| WS inventory policy | `experimental/ws_feed/pure_inventory_policy.py` | Ladder size / pause hints (QD L5 owns permissions in v2.2+) |
| Drawdown | `risk/drawdown.py` | Daily MTM kill threshold |
| Kill switch | `risk/kill_switch.py` | Persistent `logs/kill_switch.json` |
| Preflight | `utils/preflight.py` | Live gate before quoting |
| QD stack | `strategy/quote_decision_layers/` | L1 posture → L5 permissions |
| WS adapter | `experimental/ws_feed/quote_decision/` | Bridge to `PureQuotePath` |

**Reuse:** `inventory_limits`, `drawdown`, `kill_switch`, `preflight`, core L5 pipeline.  
**Trim later:** G2 toxic scaler, G4 peer-lane intel, session balance-loss kills, auto-profile switching.

---

### Bracket / paired order logic

**Finding:** No XRPL bracket orders or atomic paired bid/ask. “Brackets” = **3-level ladder** (`order_levels`, `order_sizes`, `level_spread_increment`).

| Piece | Path |
|-------|------|
| Ladder build | `experimental/ws_feed/dynamic_sizing.py` → `build_pure_quote_ladder()` |
| Pure path | `experimental/ws_feed/pure_quote_path.py` |
| Live placement | `engine/order_sync.py` → `plan_order_sync()` |
| L1-only live | `ws_pure_engine.py` — only L1 intents submit; L2/L3 diagnostic |

**Reuse:** Ladder + order sync pattern.  
**Replace:** Legacy `engine/order_manager.py` + `strategy/avellaneda_strategy.py` profile path.

---

### Logging and monitoring

| Output | Path / producer |
|--------|-----------------|
| App log | `logs/xledgermate.log` via `utils/logging_setup.py` |
| Trades | `logs/trades_YYYY-MM.csv` via `monitoring/csv_logger.py` |
| Runtime SSOT | `logs/runtime_state.json` via `core/runtime_state.py` |
| Intel cycles | `logs/intel_decisions.jsonl` (optional) |
| QD ops | `strategy/quote_decision_layers/ops_log.py` — `QD_OPS`, `QD_FINAL` |
| Transfers | `logs/transfers.csv` via `utils/send_funds.py` |
| Kill state | `logs/kill_switch.json` |

**Reuse:** `setup_logging`, CSVLogger, `runtime_state.json`.  
**Defer:** Soak dashboards, 14-report HUD catalog, Grok narrative reports.

---

## Reuse vs replace matrix

### Reuse (Trading Bot Alpha core)

1. `main.py --mode ws-engine`
2. `config/settings.py` + `config/config.yaml` + `credentials.local.yaml` loading
3. `connectors/xrpl_connector.py` + `utils/wallet_credentials.py`
4. `experimental/ws_feed/ws_pure_engine.py` (feature flags can be narrowed)
5. `experimental/ws_feed/pure_quote_path.py` + `dynamic_sizing.py`
6. `engine/order_sync.py`
7. `strategy/quote_decision_layers/` + WS `quote_decision` adapter
8. `risk/drawdown.py`, `risk/kill_switch.py`, `risk/inventory_limits.py`, `utils/preflight.py`
9. `utils/logging_setup.py`, `monitoring/csv_logger.py`
10. `monitoring/telegram_alerts.py` (optional)
11. VPS SSH deploy pattern (`scripts/vps_deploy_ashigaru.sh` — branch rename when ready)

### Replace or defer (not Alpha-critical)

| Component | Reason |
|-----------|--------|
| `engine/trading_engine.py` | Deprecated HTTP poll engine |
| `gui/streamlit_gui.py` | Heavy; Alpha can use CLI + runtime_state |
| `experimental/ws_feed/live_pure_as_tester.py` | Lab overlay |
| `pure_dry_run_executor.py` | Not production dry_run |
| Full HUD + 14 reports + Grok soak narrative | Ops luxury; trim for Alpha |
| G1/G4 competitor intel scrape | RPC cost; optional |
| `strategy/avellaneda_strategy.py` profiles | Legacy non-pure path |
| Auto-profile switching | Single-strategy Alpha |
| `Ashigaru-Shoshin` naming in user-facing strings | Rebrand to “Trading Bot Alpha” in Phase 1+ |

---

## Dry-run / live flip procedure (operator)

1. **Paper on mainnet:** `testnet: false`, `dry_run: true` → start `ws-engine`
2. **Verify:** `logs/runtime_state.json` shows `dry_run: true`, correct balances, QD fields
3. **Preflight:** `python scripts/verify_ledger_balances.py`
4. **Trustline** (if not already on ledger): `python main.py --mode setup-trust`
5. **Go live:** Set `dry_run: false` in yaml → restart engine → preflight must pass
6. **Emergency:** `python main.py --mode cancel-offers` then `clear-kill` or stop systemd unit

No code edits required to flip — **yaml only**.

---

## VPS and Cursor deployment

Current production VPS (`188.245.50.229`) runs `Ashigaru-Shoshin` via:

```powershell
ssh -i $env:USERPROFILE\.ssh\hetzner_xledgermate -o BatchMode=yes root@188.245.50.229 "bash /root/xledgermate/scripts/vps_deploy_ashigaru.sh"
```

For Alpha transition (Phase 1+):

- Point deploy script at `alpha` branch (or add `vps_deploy_alpha.sh`)
- Keep `/root/xledgermate/config/config.yaml` and `credentials.local.yaml` **in place** on server
- Restart `xledgermate` + `xledgermate-ws-hud` after pull

---

## Phase 1 preview (out of scope for Phase 0)

When implementation begins on `alpha`:

1. Rename user-facing version strings / docs to “Trading Bot Alpha”
2. Add `docs/TRADING_BOT_ALPHA.md` operator runbook (mainnet dry_run → live)
3. Narrow `ws_feature_flags` defaults for minimal Alpha
4. Optional: slim Telegram to kill alerts only
5. Do **not** move config path, credential hooks, or dry_run semantics

---

## Checklist — Phase 0 complete

- [x] Full branch evaluation (Ashigaru-Shoshin @ v2.3.2)
- [x] Credential + YAML loading pattern documented
- [x] Dry-run switch documented
- [x] Mainnet + trustline preservation confirmed
- [x] Reuse vs replace matrix produced
- [x] Branch `alpha` created and pushed (`origin/alpha` @ `d557f92`)
- [ ] Phase 1 implementation (intentionally not started)
