# Handoff README — read this first (human or AI)

**Last updated:** 2026-06-05 (Gate 2 running; **WS probe validated** on `grok-ws-feed` — not on VPS)
**Purpose:** **New Grok session → read this file first.** Replaces chat memory for VPS, Gate 2, Telegram, kills, milestones. Path: `C:\Users\micha\xledgermate\groks input\FOR_AI_AND_FUTURE_SESSIONS.md`

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
| 2026-06-05 | **WebSocket sandbox** — branch `grok-ws-feed`, folder `experimental/ws_feed/` (probe only; **not** wired to engine or VPS systemd) |
| 2026-06-05 | **WS probe validated** — 3 min run: 660 frames, 631 book applies, final mid **−0.9 bps** vs HTTP; fix = parse `tx_json`/`tx` ([PROBE_RESULTS.md](../experimental/ws_feed/PROBE_RESULTS.md)) |

*Next expected updates: first week skim report, ≥60 fills judgment (doc 05), Tier 2.5 deploy (BookOffers + `market_edge_met`), Tier 3 engine adapter when Gate 2 ends.*

---

## 1. What this project is

- **Repo:** [github.com/mdeckstine1/xledgermate](https://github.com/mdeckstine1/xledgermate) — XRPL **XRP/RLUSD** market-making bot  
- **Local path (Windows):** `C:\Users\micha\xledgermate`  
- **Gate 2 / VPS branch:** `grok-tier-2-collab` (from `tier-2-polish`) · version **~1.4.4** — **this is what runs on the server**  
- **WebSocket lab branch:** `grok-ws-feed` (from `grok-tier-2-collab`) — `experimental/ws_feed/` only; **do not deploy to VPS** until Tier 3 sign-off  
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
xledgermate/
├── experimental/ws_feed/   ← Tier 3 WebSocket sandbox (branch grok-ws-feed; NOT on VPS)
└── groks input/
    ├── FOR_AI_AND_FUTURE_SESSIONS.md   ← THIS FILE
    ├── START_HERE.md
    ├── collab/        TO_CURSOR.md · THREAD.md · OPERATOR_NOTES.md
    ├── docs/          Audits + roadmaps (01–05)
    └── vps/
        ├── 07_VPS_BEGINNER_RUNBOOK.md
        ├── dashboard/     Light monitor (8501)
        └── full_gui/      Full streamlit_gui (8502) + .exe launcher
```

| Doc | Use when |
|-----|----------|
| [docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md](docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | Pass/fail metrics, 12-week plan |
| [vps/07_VPS_BEGINNER_RUNBOOK.md](vps/07_VPS_BEGINNER_RUNBOOK.md) | First VPS setup |
| [vps/dashboard/README.md](vps/dashboard/README.md) | Light monitoring GUI |
| [vps/full_gui/README.md](vps/full_gui/README.md) | Full GUI + systemd ownership rules |
| [collab/TO_CURSOR.md](collab/TO_CURSOR.md) | **New session protocol** — paste prompts for Grok/Cursor |
| [collab/THREAD.md](collab/THREAD.md) | Grok ↔ Cursor task thread |
| [collab/OPERATOR_NOTES.md](collab/OPERATOR_NOTES.md) | Operator priorities for both AIs |
| [docs/04_...](docs/04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md) | Toxic/kill spiral |
| [../experimental/ws_feed/README.md](../experimental/ws_feed/README.md) | WebSocket sandbox layout |
| [../experimental/ws_feed/PROBE_RESULTS.md](../experimental/ws_feed/PROBE_RESULTS.md) | **Captured probe metrics + Tier 3 checklist** |

---

## 3b. Book data: poll (live) vs WebSocket (lab)

| Mode | Where | Used by |
|------|--------|---------|
| **HTTP `BookOffers` poll** | VPS + Gate 2 | `trading_engine` → `XRPLConnector.fetch_xrp_rlusd_order_book()` |
| **WebSocket subscribe** | Local `grok-ws-feed` only | `experimental/ws_feed/` — probe + future adapter |

**Poll intervals (Gate 2 `tight_spread`, `tiered_refresh_enabled: true`):** ~**15s** book poll, ~**45s** full quote refresh (profile-driven; not always the yaml `order_refresh_time_seconds`).

**Why two branches:** Gate 2 needs uninterrupted poll-only data on VPS while WS feed is built and compared offline.

### WS probe results (2026-06-05) — ready for next phase

Full tables: [experimental/ws_feed/PROBE_RESULTS.md](../experimental/ws_feed/PROBE_RESULTS.md)

| Run | Duration | WS frames | Book applies | Final WS vs HTTP mid | Verdict |
|-----|----------|-----------|--------------|----------------------|---------|
| A (broken parser) | 10 min | 2,003 | **0** | +3.6 bps, **13s stale** | Ignored all txs (`transaction` key wrong) |
| B (verbose) | 3 min | 543 | 519 | +4.1 bps | Live OfferCreate/Cancel parsing OK |
| C (summaries) | 3 min | 660 | 631 | **−0.9 bps**, age **0.4s** | **Pass** for sandbox → Tier 3 design |

**Critical fix:** rippled sends offer bodies in **`tx_json` / `tx`**, not `transaction` — see `book_messages.py` (`0f918ad`).

**Operational notes:**

- RLUSD book stream ~**3 frames/s** on mainnet (vs ~1 HTTP snapshot / 15s).
- Incremental book can drift **±10 bps** mid-run; HTTP refresh every 45s + end alignment ~1 bps.
- **`--verbose`:** one line per WS frame; without it: HTTP lines + `[WS summary]` every 30–60s.

**Local probe (no engine, no orders):**

```powershell
cd C:\Users\micha\xledgermate
git checkout grok-ws-feed
.\.venv\Scripts\python.exe -m experimental.ws_feed.run_probe --seconds 180 --summary-interval 30
```

### Tier 3 next phase (do not start on VPS during Gate 2)

1. Subscribe **bid + ask snapshots** on connect (not only deltas).
2. `BookFeed` adapter + `book_feed_mode: poll|ws|ws_with_http_fallback` in `trading_engine`.
3. Stale/drift guard: reuse `is_trustworthy_rlusd_mid`; fall back to HTTP if WS age &gt; N s or drift &gt; X bps.
4. 30+ min soak + reconnect test before merge to `grok-tier-2-collab` or VPS.

Doc **05** / **03**: WebSocket remains **Tier 3** (post–Gate 2, capital scale) — probe de-risks engineering only.

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
| **Repo on VPS** | `/root/xledgermate` (branch `tier-2-polish` or `grok-tier-2-collab` after pull — **not** `grok-ws-feed`) |
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
| VPS session kill **0.85/45** + spread kill **12** | Tier 2.5 when data justifies — **Cursor P0:** BookOffers ask fix + `market_edge_met` live block ([THREAD.md](collab/THREAD.md)) |
| Clean restart + kill clear discipline (§6b) | |
| Operator baseline ~**234 XRP** pre-bot → ~**254** XRP equiv. early pilot (2026-06-05) | |
| **WS probe validated** on `grok-ws-feed` ([PROBE_RESULTS.md](../experimental/ws_feed/PROBE_RESULTS.md)) | Tier 3: engine adapter + snapshots + soak test; **no VPS** until Gate 2 ends |

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

## 9. For AI assistants — start here (Grok / Cursor)

**Prompts and file roles:** [collab/TO_CURSOR.md](collab/TO_CURSOR.md) (protocol only — read that path first in a new tool session).

**New Grok session — operator says:**

```
Read groks input/FOR_AI_AND_FUTURE_SESSIONS.md in C:\Users\micha\xledgermate — that's the handoff. Execute, don't only advise.
```

**Grok:** This file = facts. Update **§ Milestones** when something ships. **THREAD.md** only when coordinating code with Cursor.

**Branch discipline:**

| Task | Branch | Deploy to VPS? |
|------|--------|----------------|
| Gate 2 pilot, kills, Telegram, ops | `grok-tier-2-collab` | Yes (when operator pulls) |
| WebSocket book feed | `grok-ws-feed` | **No** until Tier 3 |
| Tier 2.5 competitive (BookOffers, edge gate) | `grok-tier-2-collab` (Cursor) | Yes after review + operator OK |

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

| Branch | Purpose |
|--------|---------|
| `grok-tier-2-collab` | Gate 2 collab, handoff, VPS GUIs, operator docs — **production path for VPS** |
| `grok-ws-feed` | `experimental/ws_feed/` WebSocket lab — keep off VPS until tested |
| `tier-2-polish` | Parent; VPS may still be here until `git pull` |

`groks input/` and `experimental/` committed on feature branches. VPS may lag local until `git pull` on server — **never pull `grok-ws-feed` onto the live engine host** during Gate 2.

**Push WS work:** `git push -u origin grok-ws-feed` (local only until merge).

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