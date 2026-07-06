#!/usr/bin/env bash
# Apply stack-growth operator preset on VPS (run from repo root).
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python <<'PY'
from alpha.hud.stack_growth_preset import STACK_GROWTH_AGENT_PATCH, STACK_GROWTH_OPERATOR_OVERRIDES
from alpha.hud.skynet_agent import merge_agent_patch
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
from config.settings import BotConfig

base = BotConfig.load()
store = OperatorRuntimeStore()
merged, errors = store.patch_overrides(STACK_GROWTH_OPERATOR_OVERRIDES, base=base)
_, aerr = merge_agent_patch(STACK_GROWTH_AGENT_PATCH)
if errors or aerr:
    raise SystemExit(f"errors={errors} agent={aerr}")
eff = apply_overrides(base, merged)
print(
    "stack_growth_applied",
    f"target={eff.inventory_target_xrp_ratio}",
    f"strength_dev={eff.alpha_strength_deviation}",
    f"ta_min_sell={eff.alpha_technical_analysis.min_sell_score}",
)
PY
