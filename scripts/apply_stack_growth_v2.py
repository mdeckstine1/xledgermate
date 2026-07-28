"""One-shot apply stack-growth v2 operator overrides (VPS / local)."""
from __future__ import annotations

from alpha.hud.skynet_agent import merge_agent_patch
from alpha.hud.stack_growth_preset import STACK_GROWTH_AGENT_PATCH, STACK_GROWTH_OPERATOR_OVERRIDES
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
from config.settings import BotConfig


def main() -> None:
    base = BotConfig.load()
    store = OperatorRuntimeStore()
    merged, errors = store.patch_overrides(STACK_GROWTH_OPERATOR_OVERRIDES, base=base)
    _, aerr = merge_agent_patch(STACK_GROWTH_AGENT_PATCH)
    if errors or aerr:
        raise SystemExit(f"errors={errors} agent={aerr}")
    eff = apply_overrides(base, merged)
    print(
        "stack_growth_v2_applied",
        f"target={eff.inventory_target_xrp_ratio}",
        f"strength_dev={eff.alpha_strength_deviation}",
        f"weakness_dev={eff.alpha_weakness_deviation}",
        f"risk_pct={eff.alpha_risk_per_trade_pct}",
        f"ta_min_sell={eff.alpha_technical_analysis.min_sell_score}",
        f"sl={eff.initial_stop_loss_pct}",
        f"tp_rr={eff.take_profit_rr}",
    )


if __name__ == "__main__":
    main()
