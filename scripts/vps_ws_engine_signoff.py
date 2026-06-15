#!/usr/bin/env python3
"""Run E1 VPS ws-engine sign-off checks (local or on server)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from experimental.ws_feed.e1_vps_signoff import (  # noqa: E402
    E1SignoffCriteria,
    evaluate_e1_signoff,
    format_e1_report,
)


def _systemd_active() -> bool | None:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "xledgermate"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="E1 VPS ws-engine sign-off")
    parser.add_argument("--repo", type=Path, default=_REPO, help="Repo root")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--live", action="store_true", help="Post-live checks (dry_run=false)")
    parser.add_argument("--gate", action="store_true", help="Exit 1 if checks fail")
    args = parser.parse_args()

    crit = E1SignoffCriteria(require_dry_run=not args.live)
    report = evaluate_e1_signoff(
        repo=args.repo,
        criteria=crit,
        systemd_active=_systemd_active(),
    )

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_e1_report(report))

    if args.gate and not report.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
