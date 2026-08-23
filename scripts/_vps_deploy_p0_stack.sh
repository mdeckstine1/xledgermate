#!/usr/bin/env bash
set -euo pipefail
cd /root/xledgermate
export PYTHONPATH=/root/xledgermate

# Heal poisoned accumulation session open commits immediately
.venv/bin/python - <<'PY'
import json
from pathlib import Path
p = Path("logs/accumulation_session.json")
if p.is_file():
    d = json.loads(p.read_text(encoding="utf-8"))
    d["open_committed_rlusd"] = 0.0
    d["chase_cancels"] = int(d.get("chase_cancels") or 0)
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print("accum_session_healed open_committed=0 filled=", d.get("filled_rlusd"))
else:
    print("no accum session")
PY

find alpha/decision alpha/orders config -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
.venv/bin/python - <<'PY'
from alpha.decision.engine import DecisionEngine
from alpha.decision.accumulation_regime import AccumulationSessionTracker
from config.settings import BotConfig
print("import_ok", hasattr(DecisionEngine, "_try_strength_trim"))
cfg = BotConfig()
sess = AccumulationSessionTracker(path=__import__("pathlib").Path("logs/accumulation_session.json"))
print("remaining_rlusd", round(sess.remaining_rlusd(cfg, rlusd_balance=83.0), 2))
print("open_committed", sess.open_committed_rlusd())
PY

systemctl restart xledgermate-alpha.service
systemctl restart xledgermate-alpha-hud.service
sleep 5
systemctl is-active xledgermate-alpha xledgermate-alpha-hud
sleep 40
echo "=== activity ==="
tail -10 logs/alpha_activity.jsonl
echo "=== scorecard ==="
.venv/bin/python scripts/bot_weekly_scorecard.py 2>/dev/null | head -40
