#!/usr/bin/env bash
# Install systemd timer: hourly Telegram fill/ops report.
set -euo pipefail

ROOT="${XLEDGERMATE_ROOT:-/root/xledgermate}"
PY="${ROOT}/.venv/bin/python"
SCRIPT="${ROOT}/scripts/hourly_telegram_report.py"

if [[ ! -x "$PY" ]]; then
  echo "Missing venv python: $PY"
  exit 1
fi
if [[ ! -f "$SCRIPT" ]]; then
  echo "Missing script: $SCRIPT"
  exit 1
fi

grep -q '^telegram_enabled: true' "${ROOT}/config/config.yaml" 2>/dev/null || {
  echo "WARN: telegram_enabled is not true in config/config.yaml — reports will not send."
}

cat > /etc/systemd/system/xledgermate-hourly-report.service <<EOF
[Unit]
Description=XLedgerMate hourly Telegram report
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PY} ${SCRIPT}
EOF

cat > /etc/systemd/system/xledgermate-hourly-report.timer <<EOF
[Unit]
Description=Run XLedgerMate hourly Telegram report

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now xledgermate-hourly-report.timer
systemctl list-timers xledgermate-hourly-report.timer --no-pager

echo ""
echo "Send a test report now:"
echo "  cd ${ROOT} && ${PY} ${SCRIPT}"
echo "Dry-run:"
echo "  ${PY} ${SCRIPT} --dry-run"