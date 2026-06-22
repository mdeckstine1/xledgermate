# Legacy Market-Making Sunset Guide

**Effective:** Phase 8 — Trading Bot Alpha is the primary production bot on branch `alpha`.

---

## What is being sunset

| Component | Path / command | Role |
|-----------|----------------|------|
| WS pure A-S engine | `python main.py --mode ws-engine` | Legacy continuous MM quoting |
| WS HUD | `python main.py --mode ws-hud` (`:8765`) | Legacy MM operator dashboard |
| QD / quote decision stack | `strategy/quote_decision_layers/` | MM decision logic — **not used by Alpha** |
| Streamlit MM GUI | `gui/streamlit_gui.py` (`:8501`/`:8502`) | Legacy lab desk |

**Alpha does not import or run this code.** Alpha lives in `alpha/` and uses value-accumulation + brackets only.

---

## Branch policy (updated)

| Branch | Production use |
|--------|----------------|
| **`alpha`** | **Primary** — Trading Bot Alpha |
| `Ashigaru-Shoshin` | **Archived** — MM rollback reference only |
| `Ashigaru-Kaizen*` | Historical archive |

See also [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md).

---

## VPS services

| Service | Legacy MM | Alpha |
|---------|-----------|-------|
| Engine | `xledgermate` | `xledgermate-alpha` |
| GUI/HUD | `xledgermate-ws-hud` (`:8765`) | `xledgermate-alpha-gui` (`:8503`) |

**Rule:** Only one engine service should be **enabled** and trading live on the Bot Account.

```bash
# After Alpha cutover
systemctl disable xledgermate xledgermate-ws-hud
systemctl enable xledgermate-alpha
```

---

## Archive recommendations

1. **Tag final MM release** on `Ashigaru-Shoshin` before cutover (operator/git).
2. **Keep branch** — do not delete; needed for `alpha_rollback_to_legacy.sh`.
3. **Backup** — `scripts/alpha_backup_legacy.sh` before cutover.
4. **Docs** — MM manuals (`WS_AS_MANUAL.md`, `STRATEGY_MANUAL.md`) remain for reference; add banner pointing to [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md).
5. **Code** — no deletion in Phase 8; optional future `legacy/` move is a separate cleanup PR.

---

## Operator messaging

- README **Trading Bot Alpha** section is the entry point for new work.
- Production cutover: [`ALPHA_HANDOVER.md`](ALPHA_HANDOVER.md).
- Do not run `run.ps1` / `ws-engine` on VPS after Alpha go-live unless rolling back.

---

## Rollback window

Keep `Ashigaru-Shoshin` deployable for **30 days** after Alpha go-live via:

```bash
bash scripts/alpha_rollback_to_legacy.sh
```

After confidence period, legacy services may remain disabled but branch stays in repo.
