#!/usr/bin/env bash
# Production cutover: legacy ws-engine → Trading Bot Alpha (dry-run first).
# Run on VPS: bash scripts/alpha_cutover_vps.sh
# Options: DRY_RUN_ONLY=1 (default) | LIVE=1 to allow existing dry_run:false
set -euo pipefail

REPO="${XLEDGERMATE_ROOT:-/root/xledgermate}"
cd "${REPO}"

DRY_RUN_ONLY="${DRY_RUN_ONLY:-1}"
ALPHA_BRANCH="${ALPHA_BRANCH:-alpha}"

echo "=============================================="
echo " xLedgerMate — Alpha production cutover"
echo " Repo: ${REPO}"
echo " Branch: ${ALPHA_BRANCH}"
echo " DRY_RUN_ONLY: ${DRY_RUN_ONLY}"
echo "=============================================="

# --- Step 1: Backup ---
echo ""
echo "[1/8] Backup legacy state..."
bash scripts/alpha_backup_legacy.sh

# --- Step 2: Stop legacy (do not run both bots live) ---
echo ""
echo "[2/8] Stop legacy ws-engine + HUD..."
systemctl stop xledgermate 2>/dev/null || true
systemctl stop xledgermate-ws-hud 2>/dev/null || true
systemctl disable xledgermate 2>/dev/null || true
systemctl disable xledgermate-ws-hud 2>/dev/null || true
echo "Legacy services stopped."

# --- Step 3: Optional cancel open offers ---
if [ "${CANCEL_OFFERS:-0}" = "1" ]; then
  echo ""
  echo "[3/8] Cancel open offers on ledger..."
  .venv/bin/python main.py --mode cancel-offers || true
else
  echo ""
  echo "[3/8] Skip cancel offers (set CANCEL_OFFERS=1 to cancel)"
fi

# --- Step 4: Checkout Alpha ---
echo ""
echo "[4/8] Checkout Alpha branch..."
git fetch origin "${ALPHA_BRANCH}"
git checkout "${ALPHA_BRANCH}"
git pull origin "${ALPHA_BRANCH}"
echo "HEAD: $(git rev-parse --short HEAD)"

# --- Step 5: Dependencies ---
echo ""
echo "[5/8] Install dependencies..."
.venv/bin/pip install -q -r requirements.txt

# --- Step 6: Enforce dry_run for soak ---
echo ""
echo "[6/8] Config safety..."
if [ -f config/config.yaml ]; then
  if [ "${DRY_RUN_ONLY}" = "1" ]; then
    if grep -q '^dry_run: false' config/config.yaml; then
      sed -i 's/^dry_run: false/dry_run: true/' config/config.yaml
      echo "Set dry_run: true for soak (was false)."
    else
      echo "dry_run already true or unset — verify config/config.yaml"
    fi
  fi
  if ! grep -q '^testnet: false' config/config.yaml; then
    echo "WARN: testnet may not be false — confirm mainnet settings."
  fi
else
  echo "ERROR: config/config.yaml missing"
  exit 1
fi

# --- Step 7: Install systemd if needed ---
echo ""
echo "[7/8] systemd units..."
if [ ! -f /etc/systemd/system/xledgermate-alpha.service ]; then
  cp scripts/systemd/xledgermate-alpha.service /etc/systemd/system/
  cp scripts/systemd/xledgermate-alpha-gui.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable xledgermate-alpha
  echo "Installed xledgermate-alpha.service"
fi

# --- Step 8: Validate and start ---
echo ""
echo "[8/8] Validate and start Alpha (dry-run soak)..."
.venv/bin/python scripts/alpha_validate.py --quiet

systemctl restart xledgermate-alpha
sleep 3
systemctl is-active xledgermate-alpha

echo ""
echo "=============================================="
echo " Cutover complete — Alpha running"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Monitor: tail -f logs/alpha_activity.jsonl"
echo "  2. Status:  .venv/bin/python -m alpha status"
echo "  3. GUI:     ssh -L 8503:127.0.0.1:8503 root@VPS  → http://localhost:8503"
echo "  4. Soak 24-48h with dry_run: true"
echo "  5. Go live: edit dry_run: false, systemctl restart xledgermate-alpha"
echo ""
echo "Rollback: bash scripts/alpha_rollback_to_legacy.sh"
echo "Handover:  docs/ALPHA_HANDOVER.md"
