#!/usr/bin/env bash
# Install systemd timer: daily Alpha bag narrative Telegram report (13:00 UTC).
set -euo pipefail

ROOT="${XLEDGERMATE_ROOT:-/root/xledgermate}"
PY="${ROOT}/.venv/bin/python"
SCRIPT="${ROOT}/scripts/daily_telegram_report.py"

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

cat > /etc/systemd/system/xledgermate-daily-report.service <<EOF
[Unit]
Description=XLedgerMate daily Alpha bag narrative (Telegram)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PY} ${SCRIPT}
EOF

cat > /etc/systemd/system/xledgermate-daily-report.timer <<EOF
[Unit]
Description=Run XLedgerMate daily Alpha bag Telegram narrative

[Timer]
OnCalendar=*-*-* 13:00:00 UTC
Persistent=true
RandomizedDelaySec=180

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now xledgermate-daily-report.timer
systemctl list-timers xledgermate-daily-report.timer --no-pager

echo ""
echo "Send a test report now:"
echo "  cd ${ROOT} && ${PY} ${SCRIPT}"
echo "Dry-run:"
echo "  ${PY} ${SCRIPT} --dry-run"
