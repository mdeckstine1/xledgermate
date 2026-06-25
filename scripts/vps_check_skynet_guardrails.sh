#!/bin/bash
set -eu
cd /root/xledgermate
.venv/bin/python <<'PY'
import json
from pathlib import Path

p = Path("logs/alpha_skynet_agent.json")
if not p.is_file():
    print("missing", p)
    raise SystemExit(1)
d = json.loads(p.read_text(encoding="utf-8"))
g = d.get("guardrails") or {}
print("saved_guardrails_risk", g.get("alpha_risk_per_trade_pct"))
prop = d.get("latest_proposal") or {}
print("last_run_utc", d.get("last_run_utc"))
print("warnings", (prop.get("warnings") or [])[:5])
raw = prop.get("raw_response") or ""
if "max=2" in raw or "max=2.0" in raw:
    print("raw_response_mentions_max_2", True)
else:
    print("raw_response_mentions_max_2", False)
if "max=4" in raw or "max=4.0" in raw:
    print("raw_response_mentions_max_4", True)
PY
