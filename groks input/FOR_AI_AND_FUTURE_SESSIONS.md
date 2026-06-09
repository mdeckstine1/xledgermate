# Handoff README — read this first (human or AI)

**Last updated:** 2026-06-08 (Gate 2 running on `grok-tier-2-collab`; **WS + pure A-S + 11k predator observations + AI handoff** captured on `grok-ws-feed`)
**Purpose:** **New Grok session → read this file first.** Replaces chat memory for VPS, Gate 2, Telegram, kills, milestones. Path: `C:\Users\micha\xledgermate\groks input\FOR_AI_AND_FUTURE_SESSIONS.md`

**Maintenance rule:** Update this file (and § Milestones) when the operator hits a milestone — VPS live, clean restart, Gate 2 start/end, profile change, major incident, git deploy to VPS, etc. Also update when major experimental observations (WS pure path behavior, funding model, scaling math, P&L targets, predator wiring) are captured for implementation.

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
| 2026-06-06 | **Tier 2.5 P0 on `grok-tier-2-collab` only** — `6c1634a` BookOffers + hard `market_edge_met` gate — **not on VPS** during 2-week Gate 2 |
| 2026-06-07 | **Dual-branch discipline** — no merge `grok-ws-feed` ↔ `grok-tier-2-collab` until Gate 2 window ends; WS + pure A-S lab continues on `grok-ws-feed` |
| 2026-06-08 | **AI handoff + 11k XRP WS pure A-S predator observations captured** — updated this file (FOR_AI...) with full session details: 11k XRP-only funding (no RLUSD), XRP-heavy start + rebalance via competitive L1/L2/L3 asks to 55% target, WS pure A-S works differently (no outer hard gate / "L1 too tight" / `market_edge_met=false`), higher presence via live WS book + competitor_pressure for "skim harder", scaling/compounding (more inventory = higher *absolute* skim via larger pull, not auto wider spreads; capital grows from rebalance + skim), live ledger (36k+ XRP offers, ~208k/282k depth supportive of scale), P&L targets (~500 XRP equiv/24h potential; conservative year-end +25–45k P&L skim / 36–56k value), current code gaps (legacy gates in main engine vs committed experimental/ws_feed pure path), immediate actions (bypass gates in pure, wire pressure as A-S aggression input, dynamic sizing, aggressive L1 on rebalance). Mirrors updates to IMPLEMENTATION_PLAN.md (Tier 3 subsection) + THE_AI_DISCUSSION.md. Pushed on `grok-ws-feed`. |

*Next expected updates: Gate 2 week-1 skim + ≥60 fills (doc 05); after 2-week test — operator pull to VPS; Tier 3 WS engine adapter + pure path only after Gate 2 sign-off. 11k XRP WS A-S predator experiments / measurements on grok-ws-feed (no VPS impact during Gate 2).*

---

## 1. What this project is

- **Repo:** [github.com/mdeckstine1/xledgermate](https://github.com/mdeckstine1/xledgermate) — XRPL **XRP/RLUSD** market-making bot  
- **Local path (Windows):** `C:\Users\micha\xledgermate`  
- **Gate 2 / VPS branch:** `grok-tier-2-collab` (from `tier-2-polish`) · version **~1.4.4** — **this is what runs on the server**  
- **WebSocket lab branch:** `grok-ws-feed` (from `grok-tier-2-collab`) — `experimental/ws_feed/` only; **do not deploy to VPS** until Tier 3 sign-off · **do not merge into VPS branch** during Gate 2  
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

---

## 13. WS + pure A-S + 11k XRP predator (grok-ws-feed experimental handoff)

**This section captures the June 2026 session observations for all future Grok / AI / Cursor sessions (implementation-ready).** Work lives in `experimental/` (ws_feed/, ai_analysis/, grokster.py, market_analysis/) on the `grok-ws-feed` branch only. Sacred long-run (HTTP poll + hard `market_edge_met` gate + current Gate 2 `tight_spread` on VPS) is **never modified** — it is the data source/oracle. All WS/pure/AI changes are advisory-only or experimental until explicit post-Gate 2 sign-off + operator opt-in for any engine swap. Prior requests (tab reorg, Inventory+QR+funding flows, Intelligence tab for Grok competitor analysis, animations, ticker fixes, data loss/NameError fixes, Grok API, "skim harder and beat competitors", recurring long-run data queries on VPS logs, layout, etc.) remain in scope and are reflected here + in the plan.

**Branch / deployment facts:**
- `grok-ws-feed`: WS book feed, pure Avellaneda-Stoikov (built-in protection only), live HUD (real_time_as_hud.py with as_reservation, as_optimal_spread_pct, would_quote, as_mode="pure"), live_pure_as_tester.py, engine_adapter_example.py, grokster validation, competitor intel, Intelligence tab, Grok/xAI `/analyze_competitor` (Config-driven), AI analysis (`experimental/ai_analysis/`). **Do not deploy to VPS or merge to grok-tier-2-collab during Gate 2.**
- `grok-tier-2-collab` (VPS): sacred long-run data generator + Gate 2 pilot. WS/pure work stays off it.
- Dual-branch discipline: keep WS lab isolated until Tier 3 readiness (post-Gate 2).

**11k XRP-only funding + rebalance model (no initial RLUSD):**
- Starts 100% XRP heavy (11k XRP is the *only* funding).
- Bot uses inventory-skewed + explicit "XRP-only mode → competitive asks" L1/L2/L3 asks to sell ~4.5–5.5k XRP and build RLUSD toward 0.55 target ratio (order_levels=3, target in config, 0.12 max_leg_size_pct_of_capital).
- This front-loads positive skim (spread capture on the sells) during the rebalance window (est. 60–120 days depending on fill rate hitting the ladder).
- Once near target, two-sided quoting sustains the skim.
- WS live book + competitor_pressure make the timing/sizing of these competitive asks smarter than the polled + gated long-run behavior.
- Rebalance + realized skim both grow the capital base for later larger pulls.

**WS pure A-S path works differently from the long-run gated pure A-S (key observation):**
- No outer hard gate / "L1 too tight (e.g. 0.047% < need 0.070%)" / `market_edge_met=false — hard gate; no live quotes`.
- No legacy heuristic guards: "thin book → near-touch backoff", "edge guard → reduced size", "market edge thin → widen both sides", "hostile + weak edge → pause", toxicity no-touch, momentum pauses.
- Relies **only** on pure A-S math (in `strategy/avellaneda_strategy.py` + wiring in experimental/ws_feed/):
  - reservation = mid - gamma * inventory_skew * vol^2 * T - adverse_selection_term
  - optimal_spread anchored to live (WS) book_spread_pct * factor + A-S widen (kappa)
  - gamma=0.35, kappa=3.5 (typical)
  - size inventory-skew aware; anchored to live best_bid/ask with small backoff.
- WS feed (ws_book_feed.py): live incremental snapshots, ws_book_age_s, message_count, depth vs HTTP poll (~15s). Higher freshness → higher presence.
- Validated in grokster replays on the *exact* sacred long-run corpus: 90.7–93.8% presence vs ~10.7–11% baseline hard-gate (+80 pp lift); 93.5% flip rate on historical "Generated 0 quotes / edge thin" cases; 0% modeled high-tox risk on the extra quotes generated.
- "Too tight"/edge/momentum signals remain useful for operator logs/HUD but are **not blockers** in the pure path. The A-S reservation inside the live WS best bid/ask + built-in inv risk / adverse protection is the only quoting decision.
- In experimental code: engine_adapter_example.py / live_pure_as_tester.py explicitly "No hard gate. No legacy heuristic guards." real_time_as_hud shows pure signals.

**Scaling, inventory, skim & compounding (more inventory = higher absolute skim):**
- Larger post-rebalance inventory + realized skim profits directly enable larger absolute order_sizes / leg depth (L1 dominant for skim on best prices; L2/L3 for presence/queue/depth) while respecting the 0.12 cap.
- Capital growth example: 11k start → 30–60k+ XRP equivalent by year-end (rebalance turnover + skim capture compounds).
- Result: higher *absolute* skim (more XRP/RLUSD volume turned over at the hit rate) + true compounding (larger sizes → more hits/fills → more skim → even larger capital base for next cycle's pull).
- Does *not* automatically produce wider spreads (A-S optimal spread driven by observed book spread + volatility + kappa; more inventory mainly affects reservation shade and volume, not width).
- On tight books (common in data): pure A-S + live WS still only quotes when math supports — but far more often than the gated regime (the presence lift is the multiplier).

**Live ledger reality (supportive of scale to predator):**
- book_offers queries (mainnet, largest ~36071 XRP offers): individual offers up to 36k+ XRP on both sides; sampled total depth ~208k XRP asks / ~282k XRP bids.
- Inside market remains tight (0.04–0.13% L1 spreads, consistent with long-run).
- Supportive: bot can grow L1/L2/L3 depth significantly (hundreds → low thousands XRP) without being the sole liquidity or excessively moving the book.
- Large existing (deeper) offers provide "cover"/absorption for our rebalance sells.
- Top-of-book is still competitive (small-to-medium offers often set the tight inside) → WS freshness + competitor_pressure ("use observed spread as real for A-S inputs" when pressure low) are critical for detecting real edges vs noise and for "skim harder" decisions.

**P&L / presence targets & predator implications (conservative, grounded in data + live view):**
- Baseline: long-run +3.957 XRP net skim / 429 fills on small cap.
- WS uplift + no-gate higher presence + live user observation of ~500 XRP equivalent / 24h potential in favorable conditions.
- Conservative blended daily (rebalance high + steady growing with compounding, tempered for tight markets / flow limits): 150–300 XRP skim (vs long-run scaled baseline ~70–80 /day; higher end if 400+ sustained in good periods).
- Rebalance phase (first 60–120 days, XRP-heavy asks): +8k–15k XRP P&L (front-loaded spread capture on sells).
- Steady + compounding: additional +15–30k+ XRP.
- Year-end total net P&L (skim): +25k to +45k XRP equivalent.
- Year-end bot value: 36k–56k XRP equivalent (11k start + P&L; includes RLUSD component at target ratio after rebalance).
- Predator ("skim harder and beat competitors"): Low competitor_pressure (defensive observed spreads / weak makers) → signal to be more aggressive (tighter effective reservation via observed spread, larger L1 size, more presence exactly on those books). High pressure → A-S math naturally more defensive. Live WS + pressure lets the bot react to *real competitor behavior* (not just internal math) for timing and sizing. Large existing orders on ledger are opportunities (cover for our ladder) rather than pure threats.

**Current code position & gaps (for achieving the target):**
- Architecture committed and good: experimental/ws_feed/ (ws_book_feed, real_time_as_hud, engine_adapter_example, live_pure_as_tester — "PURE A-S (built-in protection): ... no hard gate"), grokster.py (baseline hard-gate presence vs ws_pure_presence), avellaneda_strategy.py (compute_avellaneda_quote with inv_term + adverse_term + book-anchored spread), competitor_intel + Intelligence tab in HUD, Grok/xAI API (advisory only in Config/Intelligence; never mutates A-S). Explicit commitment in code/docs: "WS + pure A-S (built-in protections ONLY) ... No hard gate. No legacy heuristic guards." XRP-only rebalance handling ("competitive asks") exists.
- Gaps (main engine still carries legacy; must close for full pure/predator scaling on the 11k instance):
  - market_edge_met, "thin book → near-touch backoff", "edge guard → reduced size", "market edge thin → widen", "hostile + weak edge → pause", "defensive only" still active in `core/dynamic_quoting_policy.py`, `strategy/quote_decision.py`, `strategy/market_microstructure.py`, trading_engine, etc. (even though experimental path aims to bypass).
  - competitor_pressure mostly advisory/display (HUD/ticker/skim_advice) — not yet first-class input to A-S (gamma/kappa, min_edge, size_multiplier, reservation shade).
  - No automatic dynamic order_size ramp tied to current capital + pressure yet.
  - WS age used for monitoring but not yet aggression modulator.
- To hit P&L / be the predator: ensure the WS pure path *actually* bypasses legacy outer gates for this deployment (force market_edge_met=True + skip size/edge reductions when as_mode=="pure" or in the pure compute path). Wire competitor_pressure deeply (low pressure → lower effective gamma / use observed spread as real / boost L1 size / more presence exactly where competitors are weak). Add dynamic sizing (e.g. L1 = min(configured, 0.06–0.08 * current XRP bal); boost asks during XRP-heavy rebalance). Use live WS (fresh age + depth) + pressure to decide "predator mode" (quote more / size up on soft books). Leverage AI/Grok (already live in Config + /analyze_competitor) for competitor address trending to inform "go harder on this maker/level" (advisory). These turn the bot from "safe high-presence MM" into the aggressive skimmer that capitalizes on defensive books/competitors while A-S math protects.

**Immediate next actions for this 11k XRP WS A-S instance (post handoff/plan capture):**
- Config tweaks (aggressive L1/L2/L3 sizes for the funded wallet, dynamic_min_edge low/false for pure path, XRP-heavy rebalance boost).
- Patch in experimental/ws_feed/ (engine_adapter / live tester / real_time_as_hud / pure path) to enforce pure A-S decision (bypass legacy market_edge / edge guard reductions when in pure mode).
- Extend AvellanedaStrategy / policy to accept + use competitor_pressure as aggression input (e.g. adjust reservation or size_mult; low pressure = skim harder).
- Add simple dynamic size helper tied to current XRP bal + pressure.
- Run live tester/HUD against the actual 11k funded instance; measure presence / fills / realized bps vs long-run baseline.
- Monitor ws_book_age + large existing orders (36k+ XRP); use pressure (and AI) to decide when/where to be the predator.
- AI-specific: Generate Grok prompt batches focused on 11k rebalance cases (XRP-heavy + large ask L1/L2/L3 + low-pressure competitor profiles from live book queries). Run replay_ai_orchestrator on fresh decisions from the funded instance + export training examples that include competitor_pressure features. Ensure Grok "analyze competitor" is prominent in HUD for trending during rebalance; log acceptance + outcome (bps delta). Extend local stub to surface "low pressure → skim harder on asks" for XRP-heavy mode. Track new metrics: "presence when competitor pressure low vs high", "AI suggestion → realized bps delta on rebalance asks".

**AI / Grok role (strictly advisory — reinforced for predator context):**
- Lives in **Intelligence tab** + **Config tab** of the real-time HUD (and main GUI stubs). Real Grok/xAI calls (provider=grok, key, model=grok-beta, enabled) via `/analyze_competitor` POST (competitor ledger r-address + on-chain scrape + book activity).
- Prompt tuned for XRPL MM (spreads, sizes, cancels, skew, pressure) + "how pure A-S can skim harder / compete here".
- Output: rich rationale + "skim harder" suggestions (e.g. "low pressure on this maker → opportunity for tighter L1 asks or larger size on the observed spread"). Appears in Intelligence tab, decision notes, logs. **Never mutates A-S reservation price, optimal spread, would_quote decision, gamma/kappa, or any quoting math** (pure A-S inside the WS book remains the sole quoting guard).
- Per-sample "AI rationale" in HUD still uses enhanced local stub (folds in competitor_pressure) for speed. Dedicated address button triggers real Grok.
- Llama3/stub path deprecated for intel use-case.
- CLI: `--intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-beta`.
- How AI helps 11k predator scale & skim harder (without touching core math): Low pressure → surfaces "scrape harder here" (tighter effective quotes, larger L1 pull, more presence on soft books) for rebalance asks and steady state. High pressure → naturally more conservative via A-S. Ties to scaling: helps identify *where* to deploy larger pull for max rake as inventory grows. Measurement: track AI suggestion acceptance + outcome delta (did following "skim harder" improve realized bps w/o tox spike?).
- See full rules + immediate AI actions in the appended section of `experimental/ai_analysis/THE_AI_DISCUSSION.md`.

**Cross-references (read these for details + code):**
- `docs/IMPLEMENTATION_PLAN.md` (Tier 3 "11k XRP-Only Funding + WS A-S Scaling to Predator (observations...)" subsection + "How the Implementation Plan Looks Now" + "To Become the Best..." list of 10; the exact prior "WS + pure A-S..." bullets are preserved).
- `experimental/ai_analysis/THE_AI_DISCUSSION.md` (new "11k XRP-Only WS A-S Deployment & AI Role in Predator Scaling" section at end; earlier sections on data asset, Grok vs local, replay_orchestrator, rules).
- `experimental/ws_feed/WS_HANDOFF.md` + `PROBE_RESULTS.md` (WS probe + Tier 3 checklist).
- `experimental/ws_feed/live_pure_as_tester.py`, `real_time_as_hud.py`, `ws_book_feed.py`, `engine_adapter_example.py`.
- `experimental/grokster.py` (presence validation numbers).
- `docs/WS_AS_MANUAL.md` (how to run the live tester + HUD, Intelligence tab, Grok config, etc.).
- `docs/STRATEGY_MANUAL.md` (plain-English strategy + competitor intel layer).
- `config/config.yaml` + `settings.py` (order_levels, order_sizes, 0.55 ratio, 0.12 cap, dynamic_min_edge_enabled, inventory_target_xrp_ratio).
- Live data artifacts from session (temp_vps_runtime.json, vps_trades_*.csv, book_offers depth calcs) for grounding.

**Rules (unchanged but reinforced by this session):**
- Everything WS/pure/AI stays in experimental/ on grok-ws-feed.
- Sacred long-run is the untouched data source.
- Use replay/grokster/orchestrator to quantify every proposed improvement on the exact same historical cases (+ new 11k run data).
- No production impact until after Gate 2 + explicit operator approval.
- AI / Grok / intel layer is **strictly advisory** — never hard rules, overrides, or mutations on pure A-S reservation math or the WS book's "would quote".
- Preserve all explicit prior requests from compaction and this conversation.

This work (observations from WS A-S bot differing from gated long-run, 11k-only funding + compounding, live depth, P&L targets, predator wiring via pressure + AI, code gaps + immediate actions) is now captured in the AI handoff, IMPLEMENTATION_PLAN.md, and THE_AI_DISCUSSION.md for implementation. Push the update, then we can talk about exact next code/config/measurement steps.

*Update this section + § Milestones + the plan + THE_AI_DISCUSSION.md when new observations land or implementation progresses on grok-ws-feed.*