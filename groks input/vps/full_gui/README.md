# Full trading GUI on VPS

Same app as local: `gui/streamlit_gui.py` — profiles, config, session insights, kill/cancel controls.

| Service | Port | Windows launcher |
|---------|------|------------------|
| Light monitor | 8501 | `../dashboard/XLedgerMate-Dashboard.exe` |
| **Full GUI (default)** | **8502** | **`XLedgerMate-Full-GUI.exe`** |

## Install on VPS (once)

```bash
bash "/root/xledgermate/groks input/vps/full_gui/install_on_vps.sh"
```

## Windows

Double-click **`XLedgerMate-Full-GUI.exe`** or Desktop shortcut **XLedgerMate Full GUI**.

Tunnel: `localhost:8502` → VPS `127.0.0.1:8502`

The `.exe` **only** opens SSH + browser. It does **not** start the trading engine.

## Engine ownership (read this)

| Component | Owner |
|-----------|--------|
| Trading engine | **`systemctl` → `xledgermate`** |
| Full GUI | Monitor + safe controls only |

### Safe

- Open Full GUI anytime
- View metrics, decisions, profiles
- **Clear kill switch**, **Cancel offers** when needed

### Avoid during Gate 2 pilot

- **Start** — spawns a second engine if systemd already runs (button should be disabled when **Running**)
- **Stop** / **Restart engine** — conflicts with systemd; use handoff §6b instead

### Clean restart (SSH)

See [FOR_AI_AND_FUTURE_SESSIONS.md](../../FOR_AI_AND_FUTURE_SESSIONS.md) §6b.

## Security

Do not expose port 8502 to the public internet — SSH tunnel only.