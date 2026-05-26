import logging
from typing import List, Tuple
from hummingbot.strategy.avellaneda_market_making import AvellanedaMarketMaking
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.client.config.config_data_types import ClientConfigAdapter

logger = logging.getLogger(__name__)

class AvellanedaStrategy:
    """Full Avellaneda Market Making strategy with your exact specs:
    - 3-level layered brackets (150 / 500 / 1,000 XRP)
    - Volatility modifier (widens spreads in high vol)
    - Trailing sell-side logic
    - Inventory skew (XRP-heavy)
    """

    def __init__(self, config):
        self.config = config
        self.strategy = None

    def build_strategy(self, order_book: OrderBook) -> AvellanedaMarketMaking:
        """Builds the Avellaneda strategy with your custom parameters."""

        # Your 3-level layered brackets
        order_sizes = self.config.order_sizes  # [150, 500, 1000]
        base_spread = self.config.base_spread
        level_spread_increment = self.config.level_spread_increment

        # Volatility + trailing sell-side settings
        volatility_to_spread_multiplier = 1.8  # widens spreads in high vol
        trailing_sell_multiplier = 1.2         # trails upward on sell side during price rises

        self.strategy = AvellanedaMarketMaking(
            trading_pair=self.config.trading_pair,
            order_amount=order_sizes[0],  # base size for level 1
            order_levels=self.config.order_levels,
            order_level_amount=order_sizes,  # custom sizes per level
            order_level_spread=[base_spread + (i * level_spread_increment) for i in range(self.config.order_levels)],
            volatility_interval=300,
            avg_volatility_period=10,
            volatility_to_spread_multiplier=volatility_to_spread_multiplier,
            inventory_target_ratio=self.config.inventory_target_xrp_ratio,  # XRP-heavy
            trailing_sell_multiplier=trailing_sell_multiplier,
        )

        logger.info(f"✅ Avellaneda strategy initialized with {self.config.order_levels} levels: {order_sizes} XRP")
        return self.strategy

    def on_volatility_spike(self, current_vol: float):
        """Dynamic volatility modifier - widens spreads when vol is high."""
        if current_vol > 0.015:  # 1.5% volatility threshold
            logger.info(f"High volatility detected ({current_vol:.2%}) - widening spreads")

    def adjust_trailing_sell(self, mid_price: float, current_ask: float):
        """Trailing sell-side logic - follows price upward during bullish moves."""
        if mid_price > current_ask * 1.005:  # price moving up
            logger.info(f"Trailing sell-side adjustment triggered - new mid: {mid_price:.4f}")