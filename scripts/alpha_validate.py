#!/usr/bin/env python3
"""Pre-cutover validation for Trading Bot Alpha — run before mainnet go-live."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from alpha.config_validator import load_validated_config
from alpha.version import ALPHA_VERSION


def _run_pytest(quiet: bool) -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_alpha_foundation.py",
        "tests/test_alpha_phase2.py",
        "tests/test_alpha_order_manager.py",
        "tests/test_alpha_phase4.py",
        "tests/test_alpha_phase5.py",
        "tests/test_alpha_phase6.py",
        "tests/test_alpha_phase7.py",
        "tests/test_alpha_integration.py",
    ]
    if quiet:
        cmd.append("-q")
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Alpha bot before cutover")
    parser.add_argument("--skip-tests", action="store_true", help="Config checks only")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    print(f"xLedgerMate Alpha v{ALPHA_VERSION} — pre-cutover validation")
    print("=" * 50)

    config, validation = load_validated_config()
    print(validation.summary())
    for err in validation.errors:
        print(f"  ERROR: {err}")
    for warn in validation.warnings:
        print(f"  WARN: {warn}")

    print()
    print(f"  dry_run:        {config.dry_run}")
    print(f"  testnet:        {config.testnet}")
    print(f"  trading_enabled:{config.trading_enabled}")
    print(f"  account:        {config.bot_account_address[:12]}…" if config.bot_account_address else "  account: (not set)")
    print(f"  issuer:         {config.resolved_rlusd_issuer()[:12]}…")

    logs = Path("logs")
    for name in ("kill_switch.json", "alpha_controls.json", "alpha_brackets.json", "alpha_activity.jsonl"):
        path = logs / name
        status = "exists" if path.exists() else "missing"
        print(f"  {name}: {status}")

    if not validation.ok:
        print("\nFAILED — fix config errors before cutover.")
        return 2

    if config.dry_run:
        print("\nOK — dry_run=true (safe for mainnet soak).")
    else:
        print("\nWARNING — dry_run=false (LIVE trading). Confirm intentionally.")

    if not args.skip_tests:
        print("\nRunning alpha test suite…")
        code = _run_pytest(args.quiet)
        if code != 0:
            print("FAILED — tests did not pass.")
            return code
        print("All alpha tests passed.")

    print("\nNext: python -m alpha status  |  python -m alpha run --max-cycles 20")
    return 0


if __name__ == "__main__":
    sys.exit(main())
