#!/usr/bin/env bash
set -euo pipefail
cd /root/xledgermate
sed -i 's/\r$//' scripts/apply_stack_growth_preset.sh
bash scripts/apply_stack_growth_preset.sh
systemctl restart xledgermate-alpha xledgermate-alpha-hud
systemctl is-active xledgermate-alpha xledgermate-alpha-hud
