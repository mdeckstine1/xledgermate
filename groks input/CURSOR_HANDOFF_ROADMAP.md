# Cursor session quick start

**Critical path (tasks + phases):** [`docs/PURE_AS_CRITICAL_PATH.md`](../docs/PURE_AS_CRITICAL_PATH.md) — **read this first** for what to build next.

**VPS / milestones:** [`FOR_AI_AND_FUTURE_SESSIONS.md`](FOR_AI_AND_FUTURE_SESSIONS.md)  
**Collab:** [`collab/THREAD.md`](collab/THREAD.md) · [`collab/TO_CURSOR.md`](collab/TO_CURSOR.md)

**Branch:** `grok-ws-feed` (experimental) · Sacred VPS: `grok-tier-2-collab` (do not merge mid–Gate 2)

---

## Run the lab

```powershell
cd C:\Users\micha\xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose `
  --intel-ai-provider grok --intel-ai-key xai-YOURKEY --intel-ai-model grok-3
```

http://127.0.0.1:8765 · State: `logs/ws_as_demo_runtime.json`

**Analyze runtime (Phase A2):**

```powershell
python -m experimental.ws_runtime_analysis
python -m experimental.ws_runtime_analysis --include-backups
```

**Stop HUD:**

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
```

---

## Must-load source files

1. `docs/PURE_AS_CRITICAL_PATH.md`
2. `experimental/ws_feed/live_pure_as_tester.py`
3. `experimental/ws_feed/engine_adapter_example.py`
4. `experimental/competitor_pressure.py`
5. `experimental/sacred_economics.py`
6. `experimental/ws_runtime_analysis.py`
7. `experimental/ai_analysis/grok_analyzer.py`
8. `docs/WS_AS_MANUAL.md`
9. `experimental/ws_feed/WS_HANDOFF.md`

---

## Golden rules

- Pure A-S reservation inside book = **only** quoting guard.
- Pressure / Grok / AI = **inputs only** (vol, size, spread anchor).
- No experimental deploy to VPS until post–Gate 2 sign-off.
- Sacred gated run = labeled corpus for replay/economics only.

---

## VPS contrast (sparse pulls only)

```powershell
ssh -i C:\Users\micha\.ssh\hetzner_xledgermate root@188.245.50.229 "tail -5 /root/xledgermate/logs/trades_2026-06.csv; head -c 2000 /root/xledgermate/logs/runtime_state.json"
```

After `clear-kill`: always `systemctl restart xledgermate`.
