# Grok's input — XLedgerMate review pack

**New session?** Read **[FOR_AI_AND_FUTURE_SESSIONS.md](FOR_AI_AND_FUTURE_SESSIONS.md)** first (VPS IP, SSH, what's installed, daily commands).

**Date:** 2026-06-05  
**Repo:** [mdeckstine1/xledgermate](https://github.com/mdeckstine1/xledgermate)  
**Local baseline:** `grok-tier-2-collab` @ **v1.4.4** (collab branch; parent `tier-2-polish`)  
**Ops:** Gate 2 pilot on Hetzner VPS — see handoff **§ Milestones**

Third-party reviews and roadmaps (separate from repo `docs/`). **Update [FOR_AI_AND_FUTURE_SESSIONS.md](FOR_AI_AND_FUTURE_SESSIONS.md) at milestones.**

## Layout

```
groks input/
├── FOR_AI_AND_FUTURE_SESSIONS.md   ← handoff + milestones (read first)
├── START_HERE.md
├── README.md          ← you are here
├── docs/              Audits, roadmaps, metrics
└── vps/               VPS runbooks, dashboard (8501), full_gui (8502)
```

## Quick links

### [docs/](docs/)

| Doc | Contents |
|-----|----------|
| [01_FULL_STACK_CODE_AUDIT.md](docs/01_FULL_STACK_CODE_AUDIT.md) | Architecture, security, quality, risks |
| [02_HOW_IT_WORKS_AND_IMPROVEMENTS.md](docs/02_HOW_IT_WORKS_AND_IMPROVEMENTS.md) | Runtime behavior + improvements |
| [05_MASTER_ROADMAP_REALISTIC_METRICS.md](docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | **★ Primary roadmap** — realistic gates & metrics |
| [04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md](docs/04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md) | Toxic / kill / profile loop |
| [03_COMPETITIVE_MARKET_MAKER_ROADMAP.md](docs/03_COMPETITIVE_MARKET_MAKER_ROADMAP.md) | Original competitive framing (superseded by 05 for numbers) |

**Start here:** [docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md](docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md)

### [vps/](vps/)

| Doc | Contents |
|-----|----------|
| **[07_VPS_BEGINNER_RUNBOOK.md](vps/07_VPS_BEGINNER_RUNBOOK.md)** | **New to VPS?** Step-by-step setup, monitoring, updates, 2-week operator duties |
| **[vps/full_gui/](vps/full_gui/)** | **Full trading GUI (8502)** — default operator UI |
| [vps/dashboard/](vps/dashboard/) | Light monitoring GUI (8501) |
| [06_TWO_WEEK_DEDICATED_HOST_SETUP.md](vps/06_TWO_WEEK_DEDICATED_HOST_SETUP.md) | Dedicated PC or VPS overview |

---

**Note:** Public GitHub `main` is v1.0.0; active pilot code is on `tier-2-polish`.