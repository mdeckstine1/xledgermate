# Trading Bot Alpha — Phase 7 Final Testing & Cutover

## Deliverables

### Testing
- `tests/test_alpha_phase7.py` — edge cases: empty book, volatile spread, proportional partial fills, kill switch, dry-run guards, config validation, state machine terminals
- `scripts/alpha_validate.py` — operator pre-cutover script (config + full pytest suite)
- Total alpha tests: **50** across 8 test modules

### Documentation
- [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) — setup, config, CLI, safety
- [`ALPHA_MAINNET_CUTOVER.md`](ALPHA_MAINNET_CUTOVER.md) — legacy → Alpha migration + rollback
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md) — operator sign-off report
- [`README.md`](../README.md) — Trading Bot Alpha section added

### Production scripts
- `scripts/alpha_validate.py`
- `scripts/alpha_rollback_to_legacy.sh`
- `scripts/vps_deploy_alpha.sh` (Phase 6)
- `scripts/systemd/xledgermate-alpha*.service`

## Run full validation

```bash
python scripts/alpha_validate.py
# or
python -m pytest tests/test_alpha_*.py -q
```

## Manual soak (operator)

```bash
python -m alpha run --max-cycles 100
tail -f logs/alpha_activity.jsonl
```

## Phase 7 completes initial Alpha build

See [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md) for go-live recommendations and open items.
