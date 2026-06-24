"""Operator-configurable technical analysis settings for Trading Bot Alpha."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Tuple

from alpha.decision.price_history import effective_sample_seconds

TA_CANDLE_INTERVAL_MIN_SECONDS = 300  # 5m
TA_CANDLE_INTERVAL_MAX_SECONDS = 9000  # 2.5h
TA_CANDLE_INTERVAL_DEFAULT_SECONDS = 300
TA_CANDLE_INTERVAL_STEP_SECONDS = 300


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

    enabled: bool = True
    mode: str = "scoring"  # scoring | strict
    min_buy_score: float = 1.5
    min_sell_score: float = 1.0
    min_breakout_score: float = 1.5
    candle_interval_seconds: int = TA_CANDLE_INTERVAL_DEFAULT_SECONDS  # 5m–2.5h; 0 = legacy bucket
    candle_bucket_samples: int = 5
    min_candles: int = 20
    candle_price_source: str = "ask"  # bid | ask | mid | last — directional long default
    sell_signal_price_source: str = "bid"  # bid series for bearish pattern context
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


def effective_ta_candle_interval_seconds(
    cfg: AlphaTechnicalAnalysisConfig,
    *,
    cycle_seconds: int,
    sample_interval_seconds: int,
) -> int:
    """Bar width in seconds (explicit interval or legacy bucket × sample period)."""
    sample_seconds = effective_sample_seconds(cycle_seconds, sample_interval_seconds)
    if int(cfg.candle_interval_seconds) > 0:
        return int(cfg.candle_interval_seconds)
    return max(sample_seconds, int(cfg.candle_bucket_samples) * sample_seconds)


def resolve_ta_candle_bucket_samples(
    cfg: AlphaTechnicalAnalysisConfig,
    *,
    cycle_seconds: int,
    sample_interval_seconds: int,
) -> int:
    """
    Samples per synthetic OHLC candle.

    When ``candle_interval_seconds`` > 0, bucket = interval / effective sample period
    (e.g. 300s interval @ 15s samples → 20-sample candles ≈ 5m bars).
    """
    sample_seconds = effective_sample_seconds(cycle_seconds, sample_interval_seconds)
    if int(cfg.candle_interval_seconds) > 0:
        return max(1, int(round(int(cfg.candle_interval_seconds) / sample_seconds)))
    return max(1, int(cfg.candle_bucket_samples))


def recommended_price_history_max_samples(
    cfg: AlphaTechnicalAnalysisConfig,
    *,
    cycle_seconds: int,
    sample_interval_seconds: int,
    floor: int = 2880,
) -> int:
    """Tick depth needed for ``min_candles`` and longest indicator lookback at current bar size."""
    bucket = resolve_ta_candle_bucket_samples(
        cfg,
        cycle_seconds=cycle_seconds,
        sample_interval_seconds=sample_interval_seconds,
    )
    max_lookback_candles = max(
        cfg.min_candles,
        cfg.elliott_wave.lookback if cfg.elliott_wave.enabled else 0,
        cfg.fibonacci.lookback if cfg.fibonacci.enabled else 0,
        cfg.fair_value_gap.lookback if cfg.fair_value_gap.enabled else 0,
        cfg.order_block.lookback if cfg.order_block.enabled else 0,
        cfg.liquidity_grab.lookback if cfg.liquidity_grab.enabled else 0,
        cfg.structure_bos.lookback if cfg.structure_bos.enabled else 0,
        cfg.consolidation.lookback if cfg.consolidation.enabled else 0,
        cfg.bollinger.period if cfg.bollinger.enabled else 0,
        cfg.rsi.period if cfg.rsi.enabled else 0,
    )
    needed = max(120, int(max_lookback_candles) * bucket + bucket * 2)
    return max(int(floor), needed)


def validate_ta_config(cfg: AlphaTechnicalAnalysisConfig) -> List[str]:
    errors: List[str] = []
    if cfg.candle_interval_seconds < 0:
        errors.append("alpha_technical_analysis.candle_interval_seconds must be >= 0")
    elif (
        cfg.candle_interval_seconds > 0
        and (
            cfg.candle_interval_seconds < TA_CANDLE_INTERVAL_MIN_SECONDS
            or cfg.candle_interval_seconds > TA_CANDLE_INTERVAL_MAX_SECONDS
        )
    ):
        errors.append(
            "alpha_technical_analysis.candle_interval_seconds must be between "
            f"{TA_CANDLE_INTERVAL_MIN_SECONDS} and {TA_CANDLE_INTERVAL_MAX_SECONDS} (5m–2.5h)"
        )
    if cfg.candle_bucket_samples < 1:
        errors.append("alpha_technical_analysis.candle_bucket_samples must be >= 1")
    if cfg.min_candles < 5:
        errors.append("alpha_technical_analysis.min_candles must be >= 5")
    if cfg.rsi.enabled and cfg.rsi.period < 2:
        errors.append("alpha_technical_analysis.rsi.period must be >= 2")
    if cfg.mode not in ("scoring", "strict"):
        errors.append("alpha_technical_analysis.mode must be scoring or strict")
    from alpha.decision.price_history import VALID_PRICE_SOURCES

    for key, src in (
        ("candle_price_source", cfg.candle_price_source),
        ("sell_signal_price_source", cfg.sell_signal_price_source),
    ):
        if (src or "").strip().lower() not in VALID_PRICE_SOURCES:
            errors.append(f"alpha_technical_analysis.{key} must be bid, ask, mid, or last")
    return errors
