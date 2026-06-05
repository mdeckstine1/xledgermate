# collab — Grok ↔ Cursor shared inbox

**Branch:** `grok-tier-2-collab` (from `tier-2-polish`)

Use this folder to **pass messages between Grok and Cursor** (and future AI sessions) without cluttering `docs/` or `vps/`.

**Primary handoff stays:** [../FOR_AI_AND_FUTURE_SESSIONS.md](../FOR_AI_AND_FUTURE_SESSIONS.md) (VPS IP, milestones, ops).  
**Collab is for:** “what we’re doing *right now*” and thread-specific notes.

---

## How to use it

| File | Who writes | Purpose |
|------|------------|---------|
| [TO_CURSOR.md](TO_CURSOR.md) | **Grok** (or operator) | Requests, context, “please implement X”, VPS state Grok observed |
| [FROM_CURSOR.md](FROM_CURSOR.md) | **Cursor** | Replies, what was merged, blockers, “done — verify on VPS” |
| [OPERATOR_NOTES.md](OPERATOR_NOTES.md) | **You** | Preferences, priorities, “don’t touch profile this week” |
| `YYYY-MM-DD-*.md` | Anyone | One-off session logs (optional) |

**Rule:** Edit the **top section** of TO_CURSOR / FROM_CURSOR with a dated header; move old blocks to the bottom under `## Archive` instead of deleting history.

---

## Prompt snippets

**Starting Grok:**
```
Read groks input/FOR_AI_AND_FUTURE_SESSIONS.md and groks input/collab/TO_CURSOR.md (and FROM_CURSOR.md if present).
```

**Starting Cursor:**
```
Read groks input/FOR_AI_AND_FUTURE_SESSIONS.md and groks input/collab/FROM_CURSOR.md (and TO_CURSOR.md if present).
```

---

## What does *not* go here

| Put in | Not in collab |
|--------|----------------|
| [../docs/](../docs/) | Long-term audits & Gate 2 metrics |
| [../vps/](../vps/) | Production install scripts, runbooks |
| [../FOR_AI_AND_FUTURE_SESSIONS.md](../FOR_AI_AND_FUTURE_SESSIONS.md) | Milestones, IP, SSH, systemd names |

When something is **shipped and stable**, summarize in **FOR_AI § Milestones** and trim collab threads.

---

## Conventions

- **No secrets** in collab files (tokens, keys, seeds).
- **VPS changes:** Grok can run them; Cursor should note what was changed in FROM_CURSOR for the repo.
- **Git:** Commit collab updates on `grok-tier-2-collab` so both tools see the same files.