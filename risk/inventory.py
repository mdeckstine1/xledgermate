from typing import Tuple

class InventorySkew:
    def __init__(self, target_xrp_ratio: float = 0.55):
        self.target_xrp_ratio = target_xrp_ratio

    def get_skew_factor(self, current_xrp_ratio: float) -> float:
        deviation = self.target_xrp_ratio - current_xrp_ratio
        return 1.0 + (deviation * 2.0)

    def should_increase_ask_size(self, current_xrp_ratio: float) -> bool:
        return current_xrp_ratio < self.target_xrp_ratio