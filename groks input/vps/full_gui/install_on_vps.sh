#!/bin/bash
# Full Streamlit trading GUI (same as local repo gui/streamlit_gui.py)
# Run on VPS: bash "/root/xledgermate/groks input/vps/full_gui/install_on_vps.sh"

set -euo pipefail

REPO="${XLEDGERMATE_ROOT:-/root/xledgermate}"
VENV="${REPO}/.venv"
GUI="${REPO}/gui/streamlit_gui.py"
UNIT=/etc/systemd/system/xledgermate-gui.service
PORT=8502

if [[ ! -f "${GUI}" ]]; then
  echo "ERROR: ${GUI} not found"
  exit 1
fi

"${VENV}/bin/pip" install -q streamlit PyYAML pandas

cat > "${UNIT}" << EOF
[Unit]
Description=XLedgerMate full operator GUI (Streamlit)
After=network-online.target xledgermate.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${REPO}
Environment=XLEDGERMATE_ROOT=${REPO}
ExecStart=${VENV}/bin/streamlit run ${GUI} --server.address 127.0.0.1 --server.port ${PORT} --server.headless true
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xledgermate-gui
systemctl restart xledgermate-gui
sleep 4
systemctl is-active xledgermate-gui
curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://127.0.0.1:${PORT}/" || true

echo ""
echo "Full GUI: http://127.0.0.1:${PORT} (SSH tunnel from Windows)"
echo "  ssh -i ~/.ssh/hetzner_xledgermate -L ${PORT}:127.0.0.1:${PORT} root@YOUR_VPS_IP"
echo "Monitoring dashboard remains on port 8501 (xledgermate-dashboard.service)"