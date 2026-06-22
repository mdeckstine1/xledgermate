"""CLI entry: python -m alpha status | run"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from alpha.runtime.application import AlphaApplication
from utils.logging_setup import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha", description="xLedgerMate Trading Bot Alpha")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="One read-only status cycle (balances, risk, report)")
    status.add_argument("--no-telegram", action="store_true", help="Skip Telegram publish")

    run = sub.add_parser("run", help="Trading loop: evaluate entries, sync brackets, execute")
    run.add_argument("--once", action="store_true", help="Single trading cycle then exit")
    run.add_argument("--max-cycles", type=int, default=None, help="Stop after N cycles")
    run.add_argument("--telegram", action="store_true", help="Telegram report each cycle")
    return parser


async def _run_status(*, telegram: bool) -> int:
    app, validation = AlphaApplication.from_config_file()
    if not validation.ok:
        logging.error("%s", validation.summary())
        for err in validation.errors:
            logging.error("  %s", err)
        return 2
    for warn in validation.warnings:
        logging.warning("config: %s", warn)
    try:
        result = await app.run_status_cycle(telegram=telegram)
        print(result.snapshot.risk.preflight_summary)
        return 0 if result.snapshot.risk.preflight_ready or app.config.dry_run else 1
    finally:
        await app.close()


async def _run_trading(*, once: bool, max_cycles: int | None, telegram: bool) -> int:
    app, validation = AlphaApplication.from_config_file()
    if not validation.ok:
        logging.error("%s", validation.summary())
        return 2
    for warn in validation.warnings:
        logging.warning("config: %s", warn)
    if once:
        try:
            result = await app.run_trading_cycle(telegram=telegram)
            print(f"decision={result.decision.action.value} reason={result.decision.reason}")
            if result.execution:
                print(f"execution executed={result.execution.executed} dry_run={result.execution.dry_run}")
            return 0
        finally:
            await app.close()
    await app.run_trading_loop(max_cycles=max_cycles, telegram_each_cycle=telegram)
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _build_parser().parse_args(argv)
    if args.command == "status":
        return asyncio.run(_run_status(telegram=not args.no_telegram))
    if args.command == "run":
        max_cycles = 1 if args.once else args.max_cycles
        return asyncio.run(
            _run_trading(once=args.once, max_cycles=max_cycles, telegram=args.telegram)
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
