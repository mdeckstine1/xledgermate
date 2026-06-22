#!/usr/bin/env bash
# Backup legacy bot state before Alpha cutover (run on VPS as root).
set -euo pipefail

REPO="${XLEDGERMATE_ROOT:-/root/xledgermate}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${REPO}/backups/pre-alpha-cutover-${STAMP}"

cd "${REPO}"
mkdir -p "${BACKUP_DIR}"

echo "=== Backup to ${BACKUP_DIR} ==="

# Git state
git rev-parse HEAD > "${BACKUP_DIR}/git_head.txt" 2>/dev/null || true
git branch --show-current > "${BACKUP_DIR}/git_branch.txt" 2>/dev/null || true

# Config (secrets — restrict permissions)
if [ -f config/config.yaml ]; then
  cp -a config/config.yaml "${BACKUP_DIR}/"
  chmod 600 "${BACKUP_DIR}/config.yaml"
fi
if [ -f config/credentials.local.yaml ]; then
  cp -a config/credentials.local.yaml "${BACKUP_DIR}/"
  chmod 600 "${BACKUP_DIR}/credentials.local.yaml"
fi

# Logs snapshot
mkdir -p "${BACKUP_DIR}/logs"
for f in kill_switch.json runtime_state.json engine.pid portfolio_snapshots.csv; do
  [ -f "logs/${f}" ] && cp -a "logs/${f}" "${BACKUP_DIR}/logs/" || true
done
[ -d logs ] && tar -czf "${BACKUP_DIR}/logs_snapshot.tgz" logs/*.json logs/*.jsonl logs/*.csv 2>/dev/null || true

# Systemd status
systemctl status xledgermate --no-pager > "${BACKUP_DIR}/systemctl_xledgermate.txt" 2>&1 || true
systemctl status xledgermate-ws-hud --no-pager > "${BACKUP_DIR}/systemctl_ws_hud.txt" 2>&1 || true

echo "Backup complete: ${BACKUP_DIR}"
echo "To restore config only: cp ${BACKUP_DIR}/config.yaml config/config.yaml"
