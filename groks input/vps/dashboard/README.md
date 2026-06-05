# VPS operator dashboard

Lightweight **read-only** Streamlit UI to see engine status, kill switch, PnL, toxic %, book, policy, and recent decisions. Lives in `groks input` (not the full trading GUI).

## What it shows

- Engine running (pid + `systemctl` for `xledgermate`)
- Kill switch + reason
- Session fills, portfolio, balance PnL, toxic ratios, cancel/fill
- Mid / bid / ask, market condition, quoting policy
- Recent decisions + open offers
- Optional: run `weekly_skim_report.py` from the UI

## Install on VPS (188.245.50.229)

### 1. Get dashboard files onto the server

**If `groks input` is in git** (after you commit/push):

```bash
cd /root/xledgermate && git pull
```

**If not on GitHub yet**, from Windows:

```powershell
cd "C:\Users\micha\xledgermate\groks input\vps\dashboard"
.\deploy_dashboard.ps1 -VpsIp 188.245.50.229
```

### 2. Install systemd service

```bash
ssh -i ~/.ssh/hetzner_xledgermate root@188.245.50.229
bash "/root/xledgermate/groks input/vps/dashboard/install_on_vps.sh"
```

Dashboard binds **127.0.0.1:8501** only (not public internet).

### 3. View from Windows (no terminal)

**Double-click:** `XLedgerMate-Dashboard.exe` (same folder) or Desktop shortcut **XLedgerMate Dashboard**.

Opens **http://localhost:8501** automatically. Keep the minimized SSH window open.

Rebuild: `launcher\build_exe.ps1` · Fallback: `start_tunnel.ps1`

## Manual run (no systemd)

```bash
cd /root/xledgermate
.venv/bin/streamlit run "groks input/vps/dashboard/streamlit_app.py" --server.address 127.0.0.1 --server.port 8501
```

## Services on the VPS

| Service | Purpose |
|---------|---------|
| `xledgermate` | Trading engine (`main.py --mode engine`) |
| `xledgermate-dashboard` | This monitoring UI |

Install engine service separately ([07_VPS_BEGINNER_RUNBOOK.md](../07_VPS_BEGINNER_RUNBOOK.md) Part 3).

## Security

- Do **not** expose port 8501 on `0.0.0.0` without auth/VPN.
- Use SSH tunnel only.
- Dashboard is **read-only** — start/stop engine via SSH or full `gui/streamlit_gui.py` if needed.