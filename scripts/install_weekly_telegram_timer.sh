#!/usr/bin/env bash
# Install systemd timer: weekly Alpha bag-growth Telegram report (Monday 09:00 UTC).
set -euo pipefail

ROOT="${XLEDGERMATE_ROOT:-/root/xledgermate}"
PY="${ROOT}/.venv/bin/python"
SCRIPT="${ROOT}/scripts/weekly_telegram_report.py"

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

cat > /etc/systemd/system/xledgermate-weekly-report.service <<EOF
[Unit]
Description=XLedgerMate weekly Alpha bag report (Telegram)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PY} ${SCRIPT}
EOF

cat > /etc/systemd/system/xledgermate-weekly-report.timer <<EOF
[Unit]
Description=Run XLedgerMate weekly Alpha bag Telegram report

[Timer]
OnCalendar=Mon *-*-* 09:00:00 UTC
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now xledgermate-weekly-report.timer
systemctl list-timers xledgermate-weekly-report.timer --no-pager

echo ""
echo "Send a test report now:"
echo "  cd ${ROOT} && ${PY} ${SCRIPT}"
echo "Dry-run:"
echo "  ${PY} ${SCRIPT} --dry-run"
