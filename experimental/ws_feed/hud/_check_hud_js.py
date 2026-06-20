#!/usr/bin/env python3
"""Pre-deploy syntax guard for embedded HUD JavaScript.

Usage: python experimental/ws_feed/hud/_check_hud_js.py
Exit 0 if OK; exit 1 on duplicate same-scope bindings or node --check failure.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HUD = Path(__file__).resolve().parent / "index.html"

# Match top-level function bodies (one nesting level for duplicate scan).
FUNC_BODY = re.compile(
    r"function\s+(\w+)\s*\([^)]*\)\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}",
    re.DOTALL,
)


def extract_scripts(html: str) -> str:
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    if not blocks:
        raise SystemExit("No <script> blocks found")
    return "\n".join(blocks)


def duplicate_bindings(js: str) -> list[tuple[str, str, int]]:
    issues: list[tuple[str, str, int]] = []
    for name, body in FUNC_BODY.findall(js):
        decls = re.findall(r"\b(?:const|let)\s+(\w+)", body)
        for ident, count in Counter(decls).items():
            if count > 1:
                issues.append((name, ident, count))
    return issues


def node_check(js: str) -> str | None:
    try:
        proc = subprocess.run(
            ["node", "--check"],
            input=js,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "node --check failed").strip()
    return None


def main() -> int:
    html = HUD.read_text(encoding="utf-8")
    js = extract_scripts(html)

    dups = duplicate_bindings(js)
    if dups:
        for func, ident, count in dups:
            print(f"DUPLICATE: {func}() declares '{ident}' {count}x in same scope", file=sys.stderr)
        return 1

    err = node_check(js)
    if err:
        print(f"SYNTAX: {err}", file=sys.stderr)
        return 1

    print(f"OK: {HUD.name} ({len(js)} bytes JS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
