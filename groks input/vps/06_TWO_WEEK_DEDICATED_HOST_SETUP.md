# Two-week dedicated host — what you need before Gate 2

**Goal:** Run `tight_spread` engine **~20–50 hours** over **2 weeks** without your daily PC sleeping, updating, or closing Cursor.

You do **not** need a powerful machine. You need **stable power, network, and a process that survives reboots**.

---

## 1. Hardware options (realistic)

| Option | Cost | Good for 2-week run? | Notes |
|--------|------|----------------------|-------|
| **Cheap mini PC** (used NUC, Beelink, etc.) | $80–250 | ✅ Best | Leave on 24/7 in one room |
| **Old laptop** (dedicated, not daily driver) | $0 if you have one | ✅ | Disable sleep, keep plugged in |
| **Second desktop** | Varies | ✅ | Same |
| **VPS / cloud VM** (Linux) | ~$5–20/mo | ✅ | No hardware; XRPL RPC from datacenter — test amendment/RPC first |
| **Same PC you use daily** | $0 | ⚠️ Poor | Sleep, reboots, Windows Update, Cursor — fragments sessions |

**Minimum specs:** 4 GB RAM, 20 GB disk, Windows 10/11 or Linux. Python 3.12 + repo + logs << 2 GB.

**Not required:** GPU, fast CPU, local XRPL node (public RPC is fine if stable — prefer `https://s1.ripple.com:51234` per your `main.py` warnings).

---

## 2. What to install on the new machine (one-time)

1. **Windows 10/11** (or Ubuntu 22.04+ if you prefer Linux).
2. **Python 3.12** — same as dev box.
3. **Git** — clone `xledgermate` from GitHub or copy folder + `.git`.
4. **Do not** commit secrets; copy only:
   - `config/config.yaml` (or `credentials.local.yaml` sidecar)
   - Or re-enter bot address + secret once on the host.

```powershell
cd C:\path\to\xledgermate
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy config\config.example.yaml config\config.yaml
# Edit config OR copy config from existing machine (USB / encrypted zip)
```

5. **Branch:** `tier-2-polish` (or whatever runs v1.4.4 today).
6. **Smoke test** (30 min): `python main.py --mode once` then `python main.py --mode engine` — confirm fills or at least cycles in `logs/decisions.jsonl`.

---

## 3. Gate 2 config on the dedicated host

Use the bundle from [05_MASTER_ROADMAP_REALISTIC_METRICS.md](../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md):

- `active_profile: tight_spread`
- `inventory_mode: market_make`
- `dynamic_min_edge_enabled: true`
- Session kill: **0.85 XRP / 45 fills** (not 0.35 / 25)
- `toxic_fill_kill_enabled: false`
- Sync **risk capital** to live portfolio in GUI once.

**Main wallet rule:** Bot secret on this machine = **bot account only**, never Mangie main.

---

## 4. How to run for two weeks (operator model)

### Option A — Engine only (recommended on dedicated box)

No need for Streamlit 24/7. Use CLI engine + check logs remotely.

```powershell
cd C:\path\to\xledgermate
.\.venv\Scripts\python.exe main.py --mode engine
```

- Stop: create `logs/engine.stop` from GUI on another machine **or** Ctrl+C on console.
- **Stopping engine does not cancel offers** — cancel when pausing overnight if you want flat book.

### Option B — GUI on another PC, engine on dedicated host

- Share `logs/` via sync (risky) or **only use Telegram** + weekly copy of `logs/` via RDP/file share.
- Simpler: RDP into dedicated host once a day, open Streamlit there:

```powershell
.\.venv\Scripts\python.exe -m streamlit run gui/streamlit_gui.py
```

### Auto-start after reboot (Windows)

1. Task Scheduler → trigger **At startup** (delay 2 min).
2. Action: `C:\path\to\xledgermate\.venv\Scripts\python.exe`  
   Args: `main.py --mode engine`  
   Start in: `C:\path\to\xledgermate`
3. Settings: restart on failure 3 times, **stop if runs > 14 days** (optional).

Or a simple `start_engine.bat` in Startup folder.

---

## 5. OS settings (critical)

| Setting | Value |
|---------|--------|
| Sleep | **Never** (plugged in) |
| Display off | OK |
| Windows Update active hours | Set to your sleep time; or pause updates for pilot window |
| Network | Ethernet preferred; Wi-Fi OK if stable |
| Firewall | Allow Python outbound HTTPS (RPC) |
| Antivirus | Exclude `.venv` and `logs` if scans stall Python |

---

## 6. Monitoring without babysitting

| Check | Frequency | How |
|-------|-----------|-----|
| Engine alive | Daily | `logs/engine.pid` exists; or Telegram if enabled |
| Kill switch | Daily | `type logs\kill_switch.json` |
| Weekly metrics | Weekly | `python scripts/weekly_skim_report.py` |
| Balance truth | Weekly | `python scripts/portfolio_bleed_analysis.py` |
| Decisions | When curious | tail `logs/decisions.jsonl` |

**Telegram** (`telegram_enabled: true` in config): kill alerts + optional heartbeat — worth enabling on unattended host.

---

## 7. Two-week calendar (realistic)

| Week | Engine hours (target) | Fills (cumulative target) | You do |
|------|------------------------|---------------------------|--------|
| 1 | 10–20 h | 25–40 | Verify no false kills; don’t change profile |
| 2 | 20–30 h more | **60+** total | Run skim report; Gate 2 Tier A check |

You do **not** need 24/7 for 336 hours. You need **enough filled hours** on a **stable config**. Thin RLUSD may be 2–6 fills/hour when on book.

---

## 8. Before the new PC arrives (on current machine)

- [ ] Export/copy `config/config.yaml` + `credentials.local.yaml` securely (encrypted USB/password manager).
- [ ] Document current `active_profile`, kill settings, RPC URL.
- [ ] Tag git commit: `git rev-parse HEAD` on `tier-2-polish`.
- [ ] Run `weekly_skim_report.py` once — baseline for comparison.
- [ ] List open offers procedure: `python main.py --mode cancel-offers` if you shut down messy.

---

## 9. VPS shortcut (if you don’t want to buy hardware yet)

- **Ubuntu 22.04**, 1 vCPU, 1–2 GB RAM (Hetzner, DigitalOcean, etc.).
- Clone repo, venv, config with secrets via **env or sidecar** (never in git).
- `systemd` unit for `main.py --mode engine` + `Restart=always`.
- **Caveat:** Test your RPC URL from that region; some hosts hit rate limits — use `s1.ripple.com` or your private node.

---

## 10. Bottom line

**Buying a cheap always-on box (or VPS) is the right prerequisite** for Gate 2 in [05_MASTER_ROADMAP_REALISTIC_METRICS.md](../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md). The bot and metrics assume **continuous engine time**, not hero sessions on a laptop that sleeps.

When the machine is ready: smoke test → Gate 2 config → Task Scheduler → weekly skim report → judge at **60 fills**, not day 3.