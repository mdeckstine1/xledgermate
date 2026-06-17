#!/usr/bin/env bash
# Idempotent: ensure hourly Telegram report timer is installed and running.
set -euo pipefail

ROOT="${XLEDGERMATE_ROOT:-/root/xledgermate}"
INSTALL="${ROOT}/groks input/vps/install_hourly_telegram_timer.sh"

if [[ ! -f /etc/systemd/system/xledgermate-hourly-report.timer ]]; then
  if [[ -x "$INSTALL" ]] || [[ -f "$INSTALL" ]]; then
    bash "$INSTALL"
    exit 0
  fi
  echo "WARN: hourly timer unit missing and install script not found: $INSTALL"
  exit 1
fi

systemctl daemon-reload
systemctl enable --now xledgermate-hourly-report.timer
systemctl is-active xledgermate-hourly-report.timer
