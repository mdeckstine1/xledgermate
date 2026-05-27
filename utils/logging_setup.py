import logging
from pathlib import Path

def setup_logging():
    """Sets up logging for the entire bot (file + console)."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "xledgermate.log"),
            logging.StreamHandler()
        ]
    )
    logging.info("XLedgerMate logging initialized")
