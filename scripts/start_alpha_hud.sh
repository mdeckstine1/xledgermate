#!/usr/bin/env bash
# Start Alpha operator HUD (FastAPI on alpha_hud_port, default 8765).
set -euo pipefail
cd "${XLEDGERMATE_ROOT:-/root/xledgermate}"

BIND="$(
  .venv/bin/python - <<'PY'
from config.settings import BotConfig

cfg = BotConfig.load()
host = (getattr(cfg, "alpha_gui_bind_host", None) or "").strip()
if not host:
    host = (cfg.hud_bind_host or "127.0.0.1").strip() or "127.0.0.1"
print(host)
PY
)"

PORT="$(
  .venv/bin/python - <<'PY'
from config.settings import BotConfig
print(int(getattr(BotConfig.load(), "alpha_hud_port", 8765) or 8765))
PY
)"

exec .venv/bin/python main.py --mode alpha-hud --hud-host "${BIND}" --hud-port "${PORT}"
