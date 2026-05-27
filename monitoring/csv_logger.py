import csv
from datetime import datetime
from pathlib import Path

class CSVLogger:
    """Monthly CSV export for tax records and performance tracking."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.filepath = self.log_dir / f"trades_{datetime.utcnow().strftime('%Y-%m')}.csv"
        self._ensure_header()

    def _ensure_header(self):
        if not self.filepath.exists():
            with open(self.filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "event", "xrp_amount", "rlusd_amount",
                    "price", "profit_xrp", "balance_after"
                ])

    def log_trade(self, event: str, xrp_amount: float, rlusd_amount: float,
                  price: float, profit_xrp: float, balance_after: float):
        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.utcnow().isoformat(),
                event,
                f"{xrp_amount:.4f}",
                f"{rlusd_amount:.4f}",
                f"{price:.6f}",
                f"{profit_xrp:.4f}",
                f"{balance_after:.4f}"
            ])
