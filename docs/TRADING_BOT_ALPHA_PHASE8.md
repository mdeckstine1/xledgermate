# Trading Bot Alpha — Phase 8 Cutover & Handover

Phase 8 completes the transition from legacy MM to Trading Bot Alpha.

## Deliverables

| Artifact | Purpose |
|----------|---------|
| [`ALPHA_HANDOVER.md`](ALPHA_HANDOVER.md) | **Primary operator handover** — cutover, go-live, monitoring, rollback |
| [`LEGACY_MM_SUNSET.md`](LEGACY_MM_SUNSET.md) | Legacy MM deprecation guidance |
| `scripts/alpha_cutover_vps.sh` | Automated VPS cutover (backup → stop legacy → Alpha dry-run) |
| `scripts/alpha_backup_legacy.sh` | Pre-cutover backup |
| `scripts/alpha_rollback_to_legacy.sh` | Emergency rollback to ws-engine |
| Updated [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md) | `alpha` as primary branch |

## Operator quick start (VPS)

```bash
bash scripts/alpha_cutover_vps.sh
tail -f logs/alpha_activity.jsonl
python -m alpha status
```

After soak → [`ALPHA_HANDOVER.md`](ALPHA_HANDOVER.md) §4 (go-live).

## Phase 8 completes initial Alpha program

Phases 0–8: specification → production handover. Future work tracked in handover §8 open items.
