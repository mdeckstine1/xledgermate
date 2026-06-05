# Handoff README — read this first (human or AI)

**Last updated:** 2026-06-05 (Gate 2 running — Telegram live, VPS kill thresholds, early positive session)
**Purpose:** This file replaces “memory” between Cursor/Grok sessions. Paste or ask the agent to read **`groks input/FOR_AI_AND_FUTURE_SESSIONS.md`** before doing VPS or trading work.

**Maintenance rule:** Update this file (and § Milestones) when the operator hits a milestone — VPS live, clean restart, Gate 2 start/end, profile change, major incident, git deploy to VPS, etc.

---

## Milestones (changelog)

| Date (UTC) | Milestone |
|------------|-----------|
| 2026-06-05 | **VPS live** — Hetzner `188.245.50.229`, repo + venv + config deployed |
| 2026-06-05 | **Monitoring** — light dashboard (8501) + **Full GUI** (8502) via SSH tunnels + Windows `.exe` launchers |
| 2026-06-05 | **Duplicate-engine incident** — GUI-started orphan vs systemd; resolved |
| 2026-06-05 | **Clean restart** — single owner = `systemctl` only; kill cleared; 0 offers; Gate 2 session baseline reset |
| 2026-06-05 | **Gate 2 pilot started** — `tight_spread`, mainnet, 2-week discipline (don’t change profile mid-run) |
| 2026-06-05 | **Branch `grok-tier-2-collab`** — handoff, VPS GUIs, operator docs pushed for Grok/Cursor collab |
| 2026-06-05 | **Hourly Telegram report** — systemd timer on VPS (`xledgermate-hourly-report.timer`) |
| 2026-06-05 | **Collab → `THREAD.md`** — single Grok ↔ Cursor file (replaced TO_/FROM_) |
| 2026-06-05 | **Telegram live on VPS** — kill alerts + hourly report; test message OK |
| 2026-06-05 | **VPS kill thresholds** — `session_balance_loss_kill_xrp: 0.85`, `min_fills: 45`, `spread_failure_kill_cycles: 12` (was 0.35/25) |
| 2026-06-05 | **Kill-loop lesson** — clear-kill alone re-fires; always **`systemctl restart`** after clear |
| 2026-06-05 | **Gate 2 early data** — portfolio ~254 XRP equiv., session spread capture positive; **18/60** fills toward judgment (snapshot) |

*Next expected updates: first week skim report, ≥60 fills judgment (doc 05), Tier 2.5 code deploy.*

---

## 1. What this project is

- **Repo:** [github.com/mdeckstine1/xledgermate](https://github.com/mdeckstine1/xledgermate) — XRPL **XRP/RLUSD** market-making bot  
- **Local path (Windows):** `C:\Users\micha\xledgermate`  
- **Active code branch:** `grok-tier-2-collab` (from `tier-2-polish`) · version **~1.4.4**  
- **GitHub `main` is stale (v1.0.0)** — real system is local / `tier-2-polish`  
- **Risk model:** Only **bot wallet** trades; main “Mangie” bag must never be configured on the VPS  
- **All live trading data** lives on VPS: `/root/xledgermate/logs/` (not on the Windows PC)

---

## 2. Operator goal (current phase)

| Phase | Status |
|-------|--------|
| Gate 1 (plumbing) | ✅ Signed off |
| Gate 2 (competitive pilot) | **In progress** — needs **~60 fills**, `tight_spread`, 2-week run |
| VPS for uninterrupted runs | ✅ **Live** — see §4 |

**Primary scoreboard:** wallet **balance PnL**, not toxic % alone. Realistic gates: [docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md](docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md)

**Known pain (why VPS):** `safe` profile + kills stopped long data runs; toxic ratio drove off-book; session kill at −0.35 XRP / 25 fills was too tight → use **0.85 / 45 fills** on Gate 2.

**Post-restart behavior (normal):** Engine may run with **0 open offers** for stretches — inventory skew (RLUSD-heavy), momentum guards, edge/size skips. That is defensive logic, not “engine down.”

---

## 3. `groks input` folder map

```
groks input/
├── FOR_AI_AND_FUTURE_SESSIONS.md   ← THIS FILE
├── START_HERE.md
├── README.md
├── collab/        Grok ↔ Cursor — THREAD.md + OPERATOR_NOTES.md
├── docs/          Audits + roadmaps (01–05)
└── vps/
    ├── 07_VPS_BEGINNER_RUNBOOK.md
    ├── 06_TWO_WEEK_DEDICATED_HOST_SETUP.md
    ├── dashboard/     Light monitor (8501)
    └── full_gui/      Full streamlit_gui (8502) + .exe launcher
```

| Doc | Use when |
|-----|----------|
| [docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md](docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | Pass/fail metrics, 12-week plan |
| [vps/07_VPS_BEGINNER_RUNBOOK.md](vps/07_VPS_BEGINNER_RUNBOOK.md) | First VPS setup |
| [vps/dashboard/README.md](vps/dashboard/README.md) | Light monitoring GUI |
| [vps/full_gui/README.md](vps/full_gui/README.md) | Full GUI + systemd ownership rules |
| [collab/THREAD.md](collab/THREAD.md) | **Grok ↔ Cursor** conversation |
| [collab/OPERATOR_NOTES.md](collab/OPERATOR_NOTES.md) | Operator priorities for both AIs |
| [docs/04_...](docs/04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md) | Toxic/kill spiral |

---

## 4. VPS — live environment (Hetzner)

| Item | Value |
|------|--------|
| **Provider** | Hetzner Cloud ([hetzner.com/cloud](https://www.hetzner.com/cloud)) — use **Cloud Console**, not Robot/KonsoleH/DNS |
| **IP** | `188.245.50.229` |
| **Hostname** | `xledgermateOL` |
| **OS** | Ubuntu 26.04 LTS |
| **SSH user** | `root` |
| **SSH key (Windows)** | `C:\Users\micha\.ssh\hetzner_xledgermate` |
| **Repo on VPS** | `/root/xledgermate` (branch `tier-2-polish`) |
| **Python** | 3.14 venv at `/root/xledgermate/.venv` |

### Systemd services (intended ownership)

| Service | What it does | Port | Windows launcher |
|---------|----------------|------|------------------|
| `xledgermate` | **Trading engine (sole owner)** | — | Do **not** start from GUI |
| `xledgermate-gui` | Full trading GUI (`gui/streamlit_gui.py`) | **8502** | **XLedgerMate Full GUI** → `localhost:8502` |
| `xledgermate-dashboard` | Light monitor GUI | **8501** | XLedgerMate Dashboard → `localhost:8501` |
| `xledgermate-hourly-report.timer` | Hourly Telegram ops/fill summary | — | `scripts/hourly_telegram_report.py` |

**Default operator UI:** Full GUI (8502). Dashboard (8501) is optional quick view.

**Telegram (VPS):** kill alerts (immediate) + hourly summary (`xledgermate-hourly-report.timer`). After **clear-kill**, run **`systemctl restart xledgermate`** — not GUI Restart. Install timer: `bash "groks input/vps/install_hourly_telegram_timer.sh"`. Manual: `.venv/bin/python scripts/hourly_telegram_report.py`

**Collab:** optional; use [collab/THREAD.md](collab/THREAD.md) only when handing work to **Cursor**. Operator often works via Grok chat only.

**Dashboard path quirk:** Space in `groks input/` breaks systemd `WorkingDirectory`; symlink: `/root/xledgermate/groks-input-dashboard` → dashboard app.

### Config on VPS

- Copied from Windows: `config/config.yaml` + `config/credentials.local.yaml`  
- **Do not commit** those files.  
- Pilot flags: `active_profile: tight_spread`, `testnet: false`, `trading_enabled: true`, `dry_run: false`
- Session kill on VPS: **0.85 XRP / 45 fills**; `telegram_enabled: true` (secrets in file only — never commit)

### What’s done vs TODO

| Done | TODO (operator / next AI session) |
|------|-----------------------------------|
| SSH, repo, venv, config on VPS | **2-week Gate 2** — no profile changes mid-run |
| Engine via `systemd` (`xledgermate`) | Accumulate **≥60 fills**; weekly skim vs doc 05 |
| Full GUI + Dashboard + Windows `.exe` tunnels | Optional: `git pull` `grok-tier-2-collab` on VPS |
| Telegram kill + **hourly** report timer | Cursor: VPS operator GUI, `config.example.yaml` Gate 2 defaults |
| VPS session kill **0.85/45** + spread kill **12** | Tier 2.5 when data justifies |
| Clean restart + kill clear discipline (§6b) | |
| Operator baseline ~**234 XRP** pre-bot → ~**254** XRP equiv. early pilot (2026-06-05) | |

---

## 5. Full GUI without a second engine (critical)

Opening the Full GUI **does not** start the engine. The `.exe` only opens an SSH tunnel + browser.

| Action | Safe? |
|--------|-------|
| Double-click **XLedgerMate-Full-GUI.exe** | ✅ Yes |
| Browse tabs, view metrics, read decisions | ✅ Yes |
| **Clear kill switch** / **Cancel offers** (when needed) | ✅ Yes |
| Click **Start** while GUI shows **Running** | ❌ Should be disabled — if enabled, risk duplicate |
| Click **Stop** or **Restart engine** in GUI | ❌ Avoid — fights `systemd` ownership |

**How the GUI knows the engine is running:** `engine_control.is_engine_running()` scans for `main.py --mode engine` on the VPS (includes systemd’s process). Status pill should show **Running** and **Start** grayed out.

**Engine restarts:** Use §6b (SSH + systemctl), not GUI **Restart engine**.

---

## 6. Engine: start / stop / kill (VPS)

```bash
# One-cycle smoke test (before 24/7 or after code change)
cd /root/xledgermate && .venv/bin/python main.py --mode once

# Start / stop 24/7 engine (normal owner)
sudo systemctl start xledgermate
sudo systemctl status xledgermate
sudo systemctl stop xledgermate    # does NOT cancel ledger offers

# Cancel all offers
cd /root/xledgermate && .venv/bin/python main.py --mode cancel-offers

# Clear kill + restart (always restart after clear)
cd /root/xledgermate && .venv/bin/python main.py --mode clear-kill
sudo systemctl restart xledgermate
```

**Logs:** `journalctl -u xledgermate -f` · `tail -f /root/xledgermate/logs/xledgermate.log` · `logs/decisions.jsonl` · `logs/runtime_state.json`

### 6b. Clean restart (no duplicate engines)

Use after kills, duplicate PIDs, or “start fresh” for Gate 2 session baselines:

```bash
ssh -i ~/.ssh/hetzner_xledgermate root@188.245.50.229   # or Windows key path below

sudo systemctl stop xledgermate
pkill -f 'main.py --mode engine' || true
sleep 2
pgrep -af 'main.py --mode engine' || echo "all engines stopped"

cd /root/xledgermate
.venv/bin/python main.py --mode clear-kill
.venv/bin/python main.py --mode cancel-offers
rm -f engine.pid engine.stop logs/engine.pid

sudo systemctl start xledgermate
systemctl is-active xledgermate
pgrep -af 'main.py --mode engine'   # expect exactly ONE line
grep kill_switch_active logs/runtime_state.json
```

**Windows one-liner (PowerShell):** run the same remote script via `ssh -i $env:USERPROFILE\.ssh\hetzner_xledgermate root@188.245.50.229 "..."`.

---

## 7. Three commands you actually need (Windows)

### A) Open a GUI (point-and-click)

| Shortcut | What | URL |
|----------|------|-----|
| **XLedgerMate Full GUI** | **Default** — full desk (monitor + controls) | **http://localhost:8502** |
| **XLedgerMate Dashboard** | Light read-only monitor | http://localhost:8501 |

Exe paths: `groks input\vps\full_gui\XLedgerMate-Full-GUI.exe` · `groks input\vps\dashboard\XLedgerMate-Dashboard.exe`

Keep the minimized **SSH** window open while using either GUI.

### B) SSH into the server

```powershell
ssh -i $env:USERPROFILE\.ssh\hetzner_xledgermate root@188.245.50.229
```

### C) Daily health (on VPS or one-liner)

```bash
systemctl is-active xledgermate xledgermate-gui
pgrep -af 'main.py --mode engine'    # must be 1 process
grep -E 'kill_switch_active|cycle_count|active_profile' /root/xledgermate/logs/runtime_state.json
cd /root/xledgermate && .venv/bin/python scripts/weekly_skim_report.py
```

---

## 8. Gate 2 config reminder (don’t drift)

```yaml
active_profile: tight_spread
inventory_mode: market_make
dynamic_min_edge_enabled: true
testnet: false
trading_enabled: true
dry_run: false
session_balance_loss_kill_xrp: 0.85
session_balance_loss_kill_min_fills: 45
spread_failure_kill_cycles: 12
toxic_fill_kill_enabled: false
```

Sync **risk capital** to live portfolio in Full GUI when editing config; for unattended VPS runs prefer editing `config/config.yaml` on server then `systemctl restart xledgermate` (not GUI Start).

---

## 9. For AI assistants — prompt snippet

Copy into a new chat:

```
Read groks input/FOR_AI_AND_FUTURE_SESSIONS.md and groks input/collab/THREAD.md in C:\Users\micha\xledgermate first.
Context: XLedgerMate XRPL MM bot, branch grok-tier-2-collab v1.4.4, Gate 2 pilot IN PROGRESS.
VPS: Hetzner 188.245.50.229, SSH key C:\Users\micha\.ssh\hetzner_xledgermate, repo /root/xledgermate.
Engine owner: systemd xledgermate ONLY — never GUI Start/Restart.
Operator UI: Full GUI SSH tunnel localhost:8502 (xledgermate-gui service).
Do not ask me to run commands — execute them. Never commit bot_secret_key.
Update FOR_AI_AND_FUTURE_SESSIONS.md when we hit milestones.
```

---

## 10. Troubleshooting quick table

| Symptom | Check |
|---------|--------|
| Can’t open :8502 | SSH tunnel / `xledgermate-gui` active? |
| Can’t open :8501 | Tunnel / `xledgermate-dashboard` active? |
| GUI empty / stale | Engine running? `runtime_state.json` mtime recent? |
| **Two engine PIDs** | `pgrep -af main.py` → §6b clean restart |
| GUI says Stopped but engine trading | Rare detection glitch — §6b before clicking Start |
| Kill switch on | `cat logs/kill_switch.json` → clear-kill + **systemctl restart** |
| SSH refused | Hetzner console → server up? Port 22? |
| 0 offers for hours | Read `decisions.jsonl` — often inventory/momentum guards (not crash) |
| Spread kill loop | Bad book RPC — v1.4.4+ skips kill on unreliable book |

---

## 11. Git note

`groks input/` committed on `tier-2-polish`. VPS may lag local until `git pull` on server.

**Refresh dashboard on VPS after local edits:**

```powershell
cd "C:\Users\micha\xledgermate\groks input\vps\dashboard"
.\deploy_dashboard.ps1
ssh -i $env:USERPROFILE\.ssh\hetzner_xledgermate root@188.245.50.229 "systemctl restart xledgermate-dashboard"
```

---

## 12. Contact / safety

- **Real money** on mainnet when `testnet: false`.  
- Stopping the engine **does not** remove offers on the ledger.  
- Prefer **balance PnL** over MTM when the book looks wrong.

*Update § Milestones and “Last updated” when IP, branch, phase, or operational playbook changes.*