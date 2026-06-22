"""Operator-configurable technical analysis settings for Trading Bot Alpha."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Tuple


def _merge_dataclass(cls: type, base: Any, data: Dict[str, Any]) -> Any:
    if not isinstance(data, dict):
        return base
    allowed = {f.name for f in fields(cls)}
    kwargs = {f.name: getattr(base, f.name) for f in fields(cls)}
    for key, value in data.items():
        if key not in allowed:
            continue
        field_type = type(getattr(base, key))
        if hasattr(field_type, "__dataclass_fields__") and isinstance(value, dict):
            kwargs[key] = _merge_dataclass(field_type, getattr(base, key), value)
        else:
            kwargs[key] = value
    return cls(**kwargs)


@dataclass
class RsiConfig:
    enabled: bool = True
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    buy_weight: float = 1.0
    sell_weight: float = 1.0


@dataclass
class StochasticConfig:
    enabled: bool = True
    k_period: int = 14
    d_period: int = 3
    smooth_k: int = 3
    oversold: float = 20.0
    overbought: float = 80.0
    buy_weight: float = 1.0
    sell_weight: float = 1.0
    breakout_weight: float = 1.0


@dataclass
class BollingerConfig:
    enabled: bool = True
    period: int = 20
    std_dev: float = 2.0
    squeeze_bandwidth_pct: float = 0.15
    buy_weight: float = 0.5
    sell_weight: float = 0.5
    breakout_weight: float = 1.5


@dataclass
class FibonacciConfig:
    enabled: bool = True
    lookback: int = 50
    levels: List[float] = field(default_factory=lambda: [0.382, 0.5, 0.618])  # YAML list
    proximity_pct: float = 0.25
    buy_weight: float = 1.0
    sell_weight: float = 1.0


@dataclass
class ElliottWaveConfig:
    enabled: bool = True
    lookback: int = 30
    impulse_weight: float = 1.0
    corrective_weight: float = 0.5


@dataclass
class CandleStreakConfig:
    enabled: bool = True
    min_green_streak: int = 3
    min_red_streak: int = 3
    buy_weight: float = 1.0
    sell_weight: float = 1.0
    breakout_weight: float = 0.5


@dataclass
class ConsolidationConfig:
    enabled: bool = True
    lookback: int = 8
    max_band_width_pct: float = 0.35
    penalty: float = 0.5


@dataclass
class PinBarConfig:
    enabled: bool = True
    min_wick_body_ratio: float = 2.0
    buy_weight: float = 1.0
    sell_weight: float = 1.0


@dataclass
class EngulfingConfig:
    enabled: bool = True
    buy_weight: float = 1.0
    sell_weight: float = 1.0
    breakout_weight: float = 1.0


@dataclass
class InsideBarConfig:
    enabled: bool = True
    buy_weight: float = 1.0
    sell_weight: float = 1.0
    breakout_weight: float = 1.5


@dataclass
class StructureBosConfig:
    enabled: bool = True
    lookback: int = 12
    buy_weight: float = 1.0
    sell_weight: float = 1.0


@dataclass
class OrderBlockConfig:
    enabled: bool = True
    lookback: int = 20
    proximity_pct: float = 0.3
    buy_weight: float = 1.0
    sell_weight: float = 1.0


@dataclass
class FairValueGapConfig:
    enabled: bool = True
    lookback: int = 30
    min_gap_pct: float = 0.05
    buy_weight: float = 1.0
    sell_weight: float = 0.5


@dataclass
class LiquidityGrabConfig:
    enabled: bool = True
    lookback: int = 20
    wick_penetration_pct: float = 0.1
    buy_weight: float = 1.5
    sell_weight: float = 1.5


@dataclass
class AlphaTechnicalAnalysisConfig:
    """Master TA config — nested under ``alpha_technical_analysis`` in config.yaml."""

    enabled: bool = False
    mode: str = "scoring"  # scoring | strict
    min_buy_score: float = 1.0
    min_sell_score: float = 1.0
    min_breakout_score: float = 1.5
    candle_bucket_samples: int = 5
    min_candles: int = 20
    rsi: RsiConfig = field(default_factory=RsiConfig)
    stochastic: StochasticConfig = field(default_factory=StochasticConfig)
    bollinger: BollingerConfig = field(default_factory=BollingerConfig)
    fibonacci: FibonacciConfig = field(default_factory=FibonacciConfig)
    elliott_wave: ElliottWaveConfig = field(default_factory=ElliottWaveConfig)
    candle_streak: CandleStreakConfig = field(default_factory=CandleStreakConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    pin_bar: PinBarConfig = field(default_factory=PinBarConfig)
    engulfing: EngulfingConfig = field(default_factory=EngulfingConfig)
    inside_bar: InsideBarConfig = field(default_factory=InsideBarConfig)
    structure_bos: StructureBosConfig = field(default_factory=StructureBosConfig)
    order_block: OrderBlockConfig = field(default_factory=OrderBlockConfig)
    fair_value_gap: FairValueGapConfig = field(default_factory=FairValueGapConfig)
    liquidity_grab: LiquidityGrabConfig = field(default_factory=LiquidityGrabConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def merge_ta_config(
    base: AlphaTechnicalAnalysisConfig,
    data: Dict[str, Any],
) -> AlphaTechnicalAnalysisConfig:
    return _merge_dataclass(AlphaTechnicalAnalysisConfig, base, data)


def validate_ta_config(cfg: AlphaTechnicalAnalysisConfig) -> List[str]:
    errors: List[str] = []
    if cfg.candle_bucket_samples < 1:
        errors.append("alpha_technical_analysis.candle_bucket_samples must be >= 1")
    if cfg.min_candles < 5:
        errors.append("alpha_technical_analysis.min_candles must be >= 5")
    if cfg.rsi.enabled and cfg.rsi.period < 2:
        errors.append("alpha_technical_analysis.rsi.period must be >= 2")
    if cfg.mode not in ("scoring", "strict"):
        errors.append("alpha_technical_analysis.mode must be scoring or strict")
    return errors
