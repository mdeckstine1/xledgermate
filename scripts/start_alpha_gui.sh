#!/usr/bin/env bash
# Start Alpha Streamlit GUI with bind host from config (falls back to hud_bind_host).
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

PORT="${ALPHA_GUI_PORT:-8503}"
exec .venv/bin/streamlit run alpha/gui/streamlit_app.py \
  --server.address "${BIND}" \
  --server.port "${PORT}" \
  --server.headless true
