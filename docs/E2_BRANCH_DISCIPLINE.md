# E2 — Branch discipline (WS + pure A-S vs sacred corpus)

**Status:** `Ashigaru` → **`Ashigaru-Kaizen`** → **`Ashigaru-Kaizen-II`** (archived v2.1.40) → **`Ashigaru-Shoshin`** (2026-06-21, v2.3.0) · **Production MM:** v2.3.0

---

## Which branch for what

| Branch | Deploy to VPS live MM? | Role |
|--------|------------------------|------|
| **`Ashigaru-Shoshin`** | **Yes** | Production: QD stack v2.2.x, `main.py --mode ws-engine`, HUD `:8765` |
| **`Ashigaru-Kaizen-II`** | No (archived) | v2.1.40 — last A2 gate + pause_bids/asks coupling |
| **`Ashigaru-Kaizen`** | No (archived) | v2.1.10 era — historical |
| **`Ashigaru`** | No (renamed) | Historical name |
| **`grok-tier-2-collab`** | No | Sacred Gate 2 labeled corpus, `grokster`, `replay_long_run`, economics A/B |
| **`grok-ws-feed`** | No (superseded) | Historical; do not use for new work |

---

## Two engines, one repo

| Mode | Command | Quoting model | Use |
|------|---------|---------------|-----|
| **WS + pure A-S** | `python main.py --mode ws-engine` | `WsPureTradingEngine` · reservation inside L1 · no hard `market_edge_met` | **Live MM on VPS** |
| **Legacy sacred** | `python main.py --mode engine` | HTTP poll + P0 hard gate (`6c1634a`) | **Replay baseline only** — compare presence/economics vs pure path |

**E2 rule:** P0 gate code stays in `engine/trading_engine.py` for sacred replay. It must **not** be wired into `ws_pure_engine.py`.

---

## Operator commands

**VPS production (Ashigaru-Shoshin):**

```bash
cd /root/xledgermate
git fetch && git checkout Ashigaru-Shoshin && git pull
systemctl restart xledgermate xledgermate-ws-hud
```

**Sacred replay / economics (any machine, collab or Ashigaru — same WS code after E2):**

```powershell
python -m experimental.grokster
python -m experimental.ws_feed.replay_long_run --as-mode pure --economics
python scripts/ws_path_session_report.py --gate-full
```

---

## Related

- [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) — Phase E checklist (QD ops grep: `docs/QUOTE_DECISION_LAYERS.md`)
- [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) — E1 ladder
- [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) — live WS + pure A-S ops
