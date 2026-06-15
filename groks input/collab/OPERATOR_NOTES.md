# Operator notes (you)

*Short priorities Grok and Cursor should respect. Edit anytime.*

---

## Current (2026-06-15 — post E2)

- **Production MM (VPS):** branch **`Ashigaru`** · `python main.py --mode ws-engine` · HUD **`:8765`** · pure A-S v**2.1.0** · **no** legacy `market_edge_met` gate on this path.
- **Sacred corpus / replay:** branch **`grok-tier-2-collab`** — Gate 2 labeled data, `replay_long_run`, `grokster`. P0 hard gate (`6c1634a`) applies to **legacy `trading_engine` replay only**, not `ws-engine`.
- **E2 merged:** WS + pure A-S code and docs live on **both** branches; operator deploys **Ashigaru** for live MM.
- **E3 blocked:** no Xaman → bot 11k transfer until local dev complete (~234 XRP-equiv pilot on bot ledger).
- **Critical path:** `docs/PURE_AS_CRITICAL_PATH.md` — Phase E1 ✓, E2 ✓, G1–G2 ✓.
- **Collab:** `groks input/collab/THREAD.md` for Grok ↔ Cursor.
- **After kill:** `clear-kill` + `systemctl restart` (not GUI Restart alone).

---

## Archive

*(older priorities)*
