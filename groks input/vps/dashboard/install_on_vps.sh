#!/bin/bash
# Install VPS operator dashboard (Streamlit) on the same host as XLedgerMate.
# Run as root on the VPS:
#   bash "/root/xledgermate/groks input/vps/dashboard/install_on_vps.sh"

set -euo pipefail

REPO="${XLEDGERMATE_ROOT:-/root/xledgermate}"
DASH="${REPO}/groks input/vps/dashboard"
VENV="${REPO}/.venv"

if [[ ! -f "${REPO}/main.py" ]]; then
  echo "ERROR: XLedgerMate repo not found at ${REPO}"
  exit 1
fi

if [[ ! -f "${DASH}/streamlit_app.py" ]]; then
  echo "ERROR: Dashboard not found at ${DASH}"
  echo "Pull latest repo or copy groks input/ from your dev machine."
  exit 1
fi

"${VENV}/bin/pip" install -q -r "${DASH}/requirements.txt"

# systemd breaks on spaces in "groks input/" — stable symlink for ExecStart
LINK="${REPO}/vps_dashboard.py"
rm -f "${LINK}"
ln -sf "${DASH}/streamlit_app.py" "${LINK}"

APP_PATH="${LINK}"
UNIT=/etc/systemd/system/xledgermate-dashboard.service

cat > "${UNIT}" << EOF
[Unit]
Description=XLedgerMate VPS operator dashboard (Streamlit)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${REPO}
Environment=XLEDGERMATE_ROOT=${REPO}
ExecStart=${VENV}/bin/streamlit run ${APP_PATH} --server.address 127.0.0.1 --server.port 8501 --server.headless true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xledgermate-dashboard
systemctl restart xledgermate-dashboard
systemctl --no-pager status xledgermate-dashboard

echo ""
echo "Dashboard listening on 127.0.0.1:8501 (localhost only)."
echo "From Windows:"
echo "  ssh -i ~/.ssh/hetzner_xledgermate -L 8501:127.0.0.1:8501 root@YOUR_VPS_IP"
echo "  Browser: http://localhost:8501"