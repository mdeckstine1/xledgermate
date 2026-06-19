#!/usr/bin/env python3
"""Activate kill switch and cancel all live offers (operator halt)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from config.settings import BotConfig
from engine import TradingEngine
from risk.kill_switch import KillSwitch


async def main() -> int:
    parser = argparse.ArgumentParser(description="Halt trading: kill switch + cancel offers")
    parser.add_argument(
        "--reason",
        default="Operator halt — G6 hold + negative session skim (soak triage)",
        help="Kill switch reason stored in logs/kill_switch.json",
    )
    args = parser.parse_args()

    ks = KillSwitch(path=ROOT / "logs" / "kill_switch.json")
    ks.activate(args.reason)
    print(f"Kill switch ON: {ks.reason}")

    config = BotConfig.load()
    engine = TradingEngine(config)
    count = await engine.cancel_all_offers()
    print(f"Cancelled {count} open offer(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
