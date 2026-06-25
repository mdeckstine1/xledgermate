"""Dump TA signal table (run: PYTHONPATH=. .venv/bin/python scripts/_ta_signals_quick.py)."""
from __future__ import annotations

import json
from pathlib import Path

from alpha.decision.ohlc_cache import cache_status, get_candles
from alpha.decision.price_history import load_price_series
from alpha.decision.ta_config import effective_ta_candle_interval_seconds
from alpha.decision.technical_analysis import TechnicalAnalysis
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
from config.settings import BotConfig


def main() -> None:
    cfg = BotConfig.load()
    ov = OperatorRuntimeStore().load_overrides()
    cfg = apply_overrides(cfg, ov)
    ta_cfg = cfg.alpha_technical_analysis
    interval = effective_ta_candle_interval_seconds(
        ta_cfg,
        cycle_seconds=cfg.alpha_cycle_interval_seconds,
        sample_interval_seconds=cfg.alpha_price_sample_interval_seconds,
    )
    logs = Path("logs")
    print("=== effective TA ===")
    print(f"candle_interval_seconds={interval}  price_source={ta_cfg.candle_price_source}")
    print(f"rsi={ta_cfg.rsi.enabled} stoch={ta_cfg.stochastic.enabled} bb={ta_cfg.bollinger.enabled}")
    print(f"engulfing={ta_cfg.engulfing.enabled} pin_bar={ta_cfg.pin_bar.enabled}")
    print(json.dumps(cache_status(logs, ta_interval_seconds=interval), indent=2))

    ohlc = get_candles(interval, logs_dir=logs)
    prices = load_price_series(ta_cfg.candle_price_source, path=logs / "alpha_price_history.json")
    snap = TechnicalAnalysis(cfg).analyze(prices, candles=ohlc if len(ohlc) >= 2 else None)
    d = snap.to_dict()
    print("\n=== summary ===")
    print(d.get("summary"))
    print(f"buy={d.get('buy_score')} sell={d.get('sell_score')} bias={d.get('bias')}")
    print("\n=== signals ===")
    for sig in d.get("signals") or []:
        fired = "FIRE" if sig.get("fired") else "----"
        print(
            f"{fired}  {sig.get('name'):16}  on={sig.get('enabled')}  "
            f"bias={sig.get('bias'):8}  score={sig.get('score'):5}  {sig.get('detail')}"
        )


if __name__ == "__main__":
    main()
