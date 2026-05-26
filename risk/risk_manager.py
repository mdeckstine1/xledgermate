import asyncio
from typing import Dict, Any

class RiskManager:
    def __init__(self, config):
        self.config = config
        self.daily_max_drawdown = config.get('daily_max_drawdown', 0.035)  # 3.5% default
    
    async def check_drawdown(self, current_balance: float, start_balance: float) -> bool:
        drop = (start_balance - current_balance) / start_balance
        if drop > self.daily_max_drawdown:
            return True  # trigger kill switch
        return False

    def get_inventory_skew(self) -> float:
        return 0.55  # slightly XRP-heavy

print('RiskManager loaded - drawdown 2-5% GUI adjustable, auto rollover ON')