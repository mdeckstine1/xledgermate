# TO_CURSOR — session protocol (read this path first)

*Not the handoff body — just **how to start** a Grok or Cursor session cleanly.*

**Full context:** [../FOR_AI_AND_FUTURE_SESSIONS.md](../FOR_AI_AND_FUTURE_SESSIONS.md)  
**Conversation:** [THREAD.md](THREAD.md) (only if Cursor ↔ Grok task in flight)  
**Operator rules:** [OPERATOR_NOTES.md](OPERATOR_NOTES.md)

---

## New Grok session

Operator says:

```
Read groks input/FOR_AI_AND_FUTURE_SESSIONS.md in C:\Users\micha\xledgermate — that's the handoff. Execute, don't only advise.
```

One-liner:

```
Read FOR_AI first — Gate 2 VPS, get up to speed.
```

**Grok:** `FOR_AI` = source of truth (IP, milestones, Telegram, kills, Gate 2). Update **§ Milestones** when something ships. Prefer **operator chat**; do not churn `THREAD.md` unless Cursor is involved.

---

## New Cursor session

```
Read groks input/FOR_AI_AND_FUTURE_SESSIONS.md and groks input/collab/THREAD.md
```

Reply in **THREAD.md** (signed `— Cursor`). Do not duplicate VPS facts here — update FOR_AI milestones when shipping.

---

## File roles (keep clean)

| File | Role |
|------|------|
| **FOR_AI_AND_FUTURE_SESSIONS.md** | Handoff + milestones + ops runbook |
| **TO_CURSOR.md** (this file) | **Protocol / prompts only** |
| **THREAD.md** | Grok ↔ Cursor task thread |
| **OPERATOR_NOTES.md** | Operator priorities |

**No secrets** in any collab file.