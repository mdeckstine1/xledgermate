# VPS beginner runbook — setup, monitor, update, 2-week test

**For:** First time running XLedgerMate on a cloud server (not your daily PC).  
**Assumes:** Ubuntu 22.04 or 24.04 on the VPS; you develop on Windows.  
**Time:** ~1–2 hours first setup; then **~5–10 minutes per day** monitoring.

Related: [06_TWO_WEEK_DEDICATED_HOST_SETUP.md](06_TWO_WEEK_DEDICATED_HOST_SETUP.md) (hardware options) · Gate 2 metrics [../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md](../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md)

---

## Part 0 — What you are building (one picture)

```
Your Windows PC          Internet          VPS (Linux)
     │                      │                  │
     │  SSH (PuTTY/Terminal)│                  │
     └──────────────────────┼──────────────────┤
                            │    Python engine │
                            │    runs 24/7     │
                            │         │        │
                            │         ▼        │
                            │    XRPL mainnet  │
                            │    (bot wallet)  │
```

- The **bot runs on the VPS**, not on your laptop.
- Your laptop is for **checking in** (SSH, optional GUI over SSH tunnel).
- **Main “Mangie” wallet** never goes on the VPS — only the **bot account** secret.

---

## Part 1 — Get a VPS (15 minutes)

### Pick a provider (any is fine for a start)

| Provider | Typical plan | Price | Why beginners use it |
|----------|--------------|-------|----------------------|
| [Hetzner](https://www.hetzner.com/cloud) | CX22: 2 vCPU, 4 GB RAM | ~€4–6/mo | Cheap, stable |
| [DigitalOcean](https://www.digitalocean.com) | Basic 1–2 GB | ~$6–12/mo | Lots of tutorials |
| [Vultr](https://www.vultr.com) | 1 vCPU, 2 GB | ~$6/mo | Simple UI |
| [Linode (Akamai)](https://www.linode.com) | Nanode | ~$5/mo | Same idea |

**Create a server:**

1. Region: choose **US or EU** close to you (latency to XRPL matters a little; not critical).
2. Image: **Ubuntu 22.04 LTS** (or 24.04).
3. Size: **2 GB RAM minimum**, **4 GB** more comfortable.
4. Authentication: **SSH key** (recommended) or root password (simpler but less secure).
5. Note the **public IP address** (e.g. `203.0.113.50`).

### Hetzner Console — volumes, firewalls, backups, etc.

When creating a server, Hetzner shows extra options. For **one bot on one VPS**, use this:

| Option | Create? | Recommendation |
|--------|---------|----------------|
| **Server** (type/location/image) | ✅ Required | **Regular Performance** CX22 (2 vCPU, 4 GB) or Cost Optimized if budget-tight; **Ubuntu 22.04**; your **SSH key** attached |
| **Volumes** | ❌ Skip | Extra disk for databases/big files. Bot + logs need **&lt; 5 GB** — built-in disk is enough |
| **Firewalls** | ✅ Yes (recommended) | Create one firewall (see below), attach to server |
| **Backups** | Optional | ~20% extra cost; snapshot restore if you break the OS. **Nice, not required** — you still backup `config.yaml` locally |
| **Placement groups** | ❌ Skip | Only for spreading **multiple** servers across hardware |
| **Labels** | Optional | e.g. `project=xledgermate` `role=gate2` — helps you find the server in Console later |
| **Cloud config** (cloud-init) | ❌ Skip first time | Automates first boot with a script. Use the **manual** steps in Part 2 until the bot runs once |

**Minimum to click Create:** image + type + SSH key + (recommended) firewall. Everything else can be default/off.

#### Firewall (recommended rules)

Create firewall **before** the server (or when creating server → add firewall):

| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | TCP | 22 | **Your home IP**/32 if stable, or `0.0.0.0/0` if IP changes often | SSH from your PC |
| Inbound | — | — | (deny other inbound) | Do **not** open 8501 (Streamlit) to the world |
| Outbound | All | — | Allow (default) | XRPL HTTPS RPC, apt, git |

The bot only needs **outbound** internet (to Ripple RPC). No inbound ports except SSH.

Find your IP: Google “what is my ip” or `curl ifconfig.me` from PowerShell.

#### Backups — if you enable

- Turn on **backups** on the server in Console (small monthly fee).
- This is **OS disk snapshot**, not a substitute for copying `config.yaml` and `logs/` off the server weekly.
- Before risky updates: **Snapshots → manual snapshot** in Console is enough for most people.

#### Labels (optional example)

```
project = xledgermate
env     = mainnet-pilot
gate    = 2
```

#### Cloud config — skip unless advanced

You do **not** need cloud-init for the runbook. Later you could paste a cloud-init script to install git/python on first boot — optional automation only.

### SSH key on Windows (if you don’t have one)

PowerShell:

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\xledgermate_vps
```

Upload the **`.pub`** file in the provider’s “SSH keys” panel when creating the server.

Connect test:

```powershell
ssh -i $env:USERPROFILE\.ssh\xledgermate_vps root@YOUR_VPS_IP
```

Type `yes` if asked about fingerprint. You should see a Linux shell prompt.

---

## Part 2 — One-time server setup (30–45 minutes)

Run these **on the VPS** (after SSH in as `root` or `ubuntu`).

### 2.1 Basics

```bash
apt update && apt upgrade -y
apt install -y git python3.12 python3.12-venv python3-pip
timedatectl set-timezone America/New_York   # change to your timezone
```

### 2.2 Create a normal user (don’t run the bot as root forever)

```bash
adduser xlm
usermod -aG sudo xlm
rsync --archive --chown=xlm:xlm ~/.ssh /home/xlm/
```

Log out and SSH as `xlm@YOUR_VPS_IP` from now on.

### 2.3 Clone the bot

```bash
cd ~
git clone https://github.com/mdeckstine1/xledgermate.git
cd xledgermate
git checkout tier-2-polish
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2.4 Config (secrets stay on the server only)

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

Set at minimum:

- `bot_account_address` — **bot** r-address only  
- `bot_secret_key` — bot family secret (`s...`)  
- `testnet: false` for mainnet  
- `xrpl_testnet_rpc_url` or use mainnet URL in your config’s resolved RPC (often `https://s1.ripple.com:51234`)  
- Gate 2 block from [05 doc](../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md):

```yaml
active_profile: tight_spread
inventory_mode: market_make
dynamic_min_edge_enabled: true
testnet: false
trading_enabled: true
dry_run: false

order_levels: 1
order_sizes: [12.0, 0.0, 0.0]

session_balance_loss_kill_xrp: 0.85
session_balance_loss_kill_min_fills: 45
spread_failure_kill_cycles: 12
toxic_fill_kill_enabled: false
max_daily_drawdown_percent: 3.5
```

Save (`Ctrl+O`, Enter, `Ctrl+X` in nano).

**Optional Telegram alerts** (recommended for monitoring):

```yaml
telegram_enabled: true
telegram_token: "YOUR_BOT_TOKEN"
telegram_chat_id: "YOUR_CHAT_ID"
```

### 2.5 Smoke test (before leaving it running)

```bash
cd ~/xledgermate
.venv/bin/python main.py --mode once
```

Expect log lines about perception / spread / preflight. Then:

```bash
ls -la logs/decisions.jsonl
tail -20 logs/decisions.jsonl
```

If that works, you are ready for the long run.

---

## Part 3 — Run the engine 24/7 (systemd)

This restarts the bot if the VPS reboots.

```bash
sudo nano /etc/systemd/system/xledgermate.service
```

Paste (adjust user/path if different):

```ini
[Unit]
Description=XLedgerMate trading engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=xlm
WorkingDirectory=/home/xlm/xledgermate
ExecStart=/home/xlm/xledgermate/.venv/bin/python main.py --mode engine
Restart=on-failure
RestartSec=30
# Graceful stop: engine checks logs/engine.stop
KillSignal=SIGINT
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable xledgermate
sudo systemctl start xledgermate
sudo systemctl status xledgermate
```

**Useful commands (memorize these):**

| What you want | Command |
|---------------|---------|
| Is it running? | `sudo systemctl status xledgermate` |
| Live logs | `journalctl -u xledgermate -f` (Ctrl+C to exit) |
| Stop engine | `sudo systemctl stop xledgermate` |
| Start engine | `sudo systemctl start xledgermate` |
| Restart engine | `sudo systemctl restart xledgermate` |

**Stop without systemd** (same as GUI stop file):

```bash
touch ~/xledgermate/logs/engine.stop
# Engine exits on next cycle; systemd may restart it unless you stop the service:
sudo systemctl stop xledgermate
```

**Cancel all offers on ledger** (when pausing for days off):

```bash
cd ~/xledgermate && .venv/bin/python main.py --mode cancel-offers
```

**Clear kill switch** (after reviewing why it fired):

```bash
cd ~/xledgermate && .venv/bin/python main.py --mode clear-kill
sudo systemctl restart xledgermate
```

Always **restart engine after clear-kill** so session baselines reset.

---

## Part 4 — How to monitor (daily ~5 min)

You do **not** need a GUI open 24/7. Three layers:

### Layer 1 — Telegram (easiest)

If enabled, you get kill-switch messages on your phone. No SSH required for emergencies.

### Layer 2 — SSH quick health check

From Windows PowerShell:

```powershell
ssh xlm@YOUR_VPS_IP
```

On VPS:

```bash
# Running?
systemctl is-active xledgermate

# Kill switch?
cat ~/xledgermate/logs/kill_switch.json 2>/dev/null || echo "no kill file"

# Last decisions
tail -5 ~/xledgermate/logs/decisions.jsonl

# Weekly metrics script
cd ~/xledgermate && .venv/bin/python scripts/weekly_skim_report.py
```

| What you see | Meaning |
|--------------|---------|
| `active` | Engine service up |
| `kill_switch.json` with `"active": true` | Bot halted — read `reason`, fix, clear-kill, restart |
| Decisions cycling | Bot thinking each poll |
| Skim report fills growing | Test progressing |

### Layer 3 — Wallet truth (weekly, non-negotiable)

Compare **bot account balance** in Xaman / explorer vs last week.  
Run on VPS:

```bash
cd ~/xledgermate && .venv/bin/python scripts/portfolio_bleed_analysis.py
```

**Scoreboard = wallet balance change**, not only GUI numbers.

### Optional — Streamlit GUI on VPS (not required)

SSH tunnel from Windows:

```powershell
ssh -L 8501:127.0.0.1:8501 xlm@YOUR_VPS_IP
```

On VPS (second SSH session or `screen`):

```bash
cd ~/xledgermate && .venv/bin/streamlit run gui/streamlit_gui.py --server.address 127.0.0.1
```

Browser on PC: `http://localhost:8501`

---

## Part 5 — How to update the bot (when you pull new code)

**During the 2-week test:** avoid updates unless fixing a bug or security issue. **Same config, same profile** = valid metrics.

When you do need an update:

```bash
sudo systemctl stop xledgermate
cd ~/xledgermate
git fetch origin
git pull origin tier-2-polish
.venv/bin/pip install -r requirements.txt
# config.yaml is NOT overwritten by git if it's gitignored — your secrets stay
sudo systemctl start xledgermate
```

**Never** `git add config/config.yaml` or paste secrets into GitHub.

If kill was active before update: `clear-kill` then restart (see Part 3).

---

## Part 6 — What to do during the 2-week test

This is your **operator job**. The VPS runs the bot; **you** verify metrics and avoid breaking the experiment.

### Before day 1

- [ ] VPS smoke test (`--mode once`) passed  
- [ ] `tight_spread` + Gate 2 kills in config (§2.4)  
- [ ] `systemctl enable` + `start` — engine running  
- [ ] Telegram on OR calendar reminder for daily SSH check  
- [ ] Baseline: run `weekly_skim_report.py`, save output in a note  

### Rules for the whole 2 weeks

| Do | Don’t |
|----|--------|
| Leave profile **`tight_spread`** | Switch to `safe` / `profit_mode` mid-test |
| Restart engine after **clear-kill** | Clear kill and leave old session baselines |
| Check daily (~5 min) | Panic-tune on toxic after 5 fills |
| Let it run **10–20+ hours/week** | Expect 100 fills in 2 days on thin RLUSD |
| Cancel offers when **off for 2+ days** | Assume stop = flat book |
| Record kill reasons in a note | Ignore repeated spread-fail kills |

### Daily checklist (~5 minutes)

1. `systemctl is-active xledgermate` → `active`  
2. `cat logs/kill_switch.json` → inactive, or read reason and follow [04 doc](../docs/04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md)  
3. `tail -3 logs/decisions.jsonl` — cycles moving?  
4. If Telegram fired overnight — investigate before restart  

**Only if kill fired:**

1. Read reason in `kill_switch.json`  
2. `weekly_skim_report.py` — fills, capture, toxic  
3. If **false** spread kill on bad book → note for engineering; restart after v1.4.4+ should be rare  
4. If **real** session loss → expected on thin book; clear-kill only if you accept risk and understand why  
5. `clear-kill` → `systemctl restart xledgermate`  

### Twice per week (~10 minutes)

```bash
cd ~/xledgermate
.venv/bin/python scripts/weekly_skim_report.py
.venv/bin/python scripts/analyze_session.py
```

Write in `logs/review_YYYY-MM-DD.md` (template in [05 doc §6](../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md)):

- Fills count (cumulative)  
- Weekly wallet balance Δ (XRP) — from explorer  
- Toxic % (only interpret if **≥ 12 fills** since restart)  
- Did you change anything? (should be **no**)  

### End of week 1 — decision

| Signal | Action |
|--------|--------|
| ≥ 25 fills, no false kills, engine stable | **Continue** week 2 unchanged |
| Kill every < 15 fills, session loss | Loosen session kill to 0.85/45 (if not already), confirm `tight_spread` |
| 0 fills, decisions show off-book always | Confirm `market_make`, dynamic edge on — not VPS issue |
| RPC / spread fail streak | Check RPC URL; try `s1.ripple.com` |

### End of week 2 — Gate 2 check

From [05](../docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md):

- [ ] **≥ 60 fills** cumulative, same config  
- [ ] **Weekly balance PnL ≥ 0** (wallet, not MTM alone)  
- [ ] Capture sum positive in skim report  
- [ ] Toxic ≤ 32% over last 50 fills **or** improving vs first 25  
- [ ] `cancel_per_fill` not worse than ~1.66 baseline  

Pass → plan Gate 3 size steps. Fail → diagnose with [04](../docs/04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md), don’t buy more capital.

### When you are on vacation / can’t SSH

- Telegram for kills  
- Trust systemd to restart after VPS reboot  
- Accept you won’t tune mid-flight — that is OK for a valid test  

---

## Part 7 — Troubleshooting

| Problem | Fix |
|---------|-----|
| Can’t SSH | Check IP, firewall allows port 22, key uploaded |
| `systemctl` failed | `journalctl -u xledgermate -n 50` — often missing config or bad secret |
| Engine runs but no fills | Thin book + defensive policy — read decisions; may be normal hours |
| Kill: session balance | Real loss; review fills CSV; adjust kill only between test windows |
| Kill: spread check 8+ | Bad quotes or bad book; check `decisions.jsonl` spread_check lines |
| `amendmentBlocked` RPC | Change RPC to `https://s1.ripple.com:51234` in config |
| Forgot to cancel offers | `main.py --mode cancel-offers` |

---

## Part 8 — Security minimum

- SSH key only; disable password login when comfortable  
- Bot secret **only** in `config/config.yaml` on VPS (chmod `600`)  
- `chmod 600 ~/xledgermate/config/config.yaml`  
- Do not expose Streamlit to `0.0.0.0` without a password / VPN  
- Firewall: `sudo ufw allow OpenSSH` then `sudo ufw enable`  

---

## Cheat sheet (print this)

```
VPS IP: _______________
SSH:    ssh xlm@IP

Status:   sudo systemctl status xledgermate
Logs:     journalctl -u xledgermate -f
Report:   cd ~/xledgermate && .venv/bin/python scripts/weekly_skim_report.py
Kill?:    cat ~/xledgermate/logs/kill_switch.json
Clear:    .venv/bin/python main.py --mode clear-kill && sudo systemctl restart xledgermate
Cancel:   .venv/bin/python main.py --mode cancel-offers

2-week test profile: tight_spread (don't change)
Daily: 5 min health check
Weekly: skim report + wallet balance on explorer
```

---

*You are not supposed to babysit charts. You are supposed to keep the process alive, record kills, and judge at 60 fills with the metrics in doc 05.*

**Handoff note (2026-06-10):** Full experimental pure A-S + WS + real Grok exploitation context (post cash addition, live HUD at :8765, 5 competitors, exploitation prompts) + complete Cursor switch package is in groks input/CURSOR_HANDOFF_ROADMAP.md. See also docs/WS_AS_MANUAL.md. All experimental work advisory-only on grok-ws-feed; sacred Gate 2 (VPS) untouched.

