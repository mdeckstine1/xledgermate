# START HERE (human)

You said VPS setup is outside your comfort zone — **that part is done.** You are in the **Gate 2 two-week pilot**.

## Daily routine (2 minutes)

1. Double-click **XLedgerMate Full GUI** → http://localhost:8502 (keep SSH window open)
2. Confirm status **Running**, kill switch **off**
3. Glance at portfolio / session PnL / open offers

Optional: **XLedgerMate Dashboard** on :8501 for a lighter view only.

**Do not click Start or Restart engine** in the Full GUI — the VPS engine is owned by `systemd`.

---

## Cheat sheet

| File | Use |
|------|-----|
| **[FOR_AI_AND_FUTURE_SESSIONS.md](FOR_AI_AND_FUTURE_SESSIONS.md)** | VPS IP, SSH, milestones, clean restart |
| **[collab/THREAD.md](collab/THREAD.md)** | **Grok ↔ Cursor** — one thread file |
| **[collab/OPERATOR_NOTES.md](collab/OPERATOR_NOTES.md)** | Your priorities both AIs should respect |

---

## What’s already done

| Step | Status |
|------|--------|
| SSH key on Windows | ✅ |
| Hetzner VPS `188.245.50.229` | ✅ |
| Bot installed on server | ✅ |
| Your config copied (secrets on VPS only) | ✅ |
| Light dashboard (8501) | ✅ |
| **Full trading GUI (8502)** | ✅ **use this daily** |
| 24/7 engine via systemd | ✅ |
| Clean single-engine restart | ✅ (2026-06-05) |
| Gate 2 pilot (`tight_spread`) | ✅ **in progress** |
| WebSocket book feed (Tier 3) | ✅ **probe validated** locally — see `experimental/ws_feed/PROBE_RESULTS.md` (VPS still HTTP poll) |

---

## New Grok session (get up to speed)

Protocol: **`groks input/collab/TO_CURSOR.md`** · Handoff: **`FOR_AI_AND_FUTURE_SESSIONS.md`**

Say: **"Read FOR_AI — that's the handoff."** (or use the exact paste in TO_CURSOR.)

## If something looks wrong

**"Read FOR_AI and check the VPS."**

For kill switch: clear in GUI or CLI, then **restart via systemd** (not GUI Restart) — see handoff §6b.