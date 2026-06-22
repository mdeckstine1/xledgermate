# Trading Bot Alpha — Phase 6 GUI & Production

## GUI

Streamlit operator panel at `alpha/gui/streamlit_app.py`:

```bash
python main.py --mode alpha-gui
# or
streamlit run alpha/gui/streamlit_app.py --server.port 8503
```

Features:
- Live portfolio, inventory %, session P&L, drawdown
- Bracket status (pending / fixed / trailing)
- Pause / resume trading (`logs/alpha_controls.json`)
- Clear kill switch
- Config read-only view (secrets redacted)
- Recent activity log (`logs/alpha_activity.jsonl`)

SSH tunnel (VPS): `ssh -L 8503:127.0.0.1:8503 root@VPS`

## Advanced features (MVP)

| Feature | Module | Status |
|---------|--------|--------|
| HTF structure stub | `alpha/decision/structure.py` | Rolling mean + breakout flags |
| Breakout trailing | `alpha/orders/trailing.py` | Mode transition on breakout |
| Bracket persistence | `alpha/orders/state.py` | `logs/alpha_brackets.json` |
| Activity log | `alpha/operator/activity.py` | JSONL audit trail |
| Enhanced Telegram | `alpha/reporting/service.py` | Structure + pause in reports |

## Testing

```bash
python -m pytest tests/test_alpha_foundation.py tests/test_alpha_phase2.py \
  tests/test_alpha_order_manager.py tests/test_alpha_phase4.py \
  tests/test_alpha_phase5.py tests/test_alpha_phase6.py \
  tests/test_alpha_integration.py -q
```

## Production systemd

Copy units from `scripts/systemd/`:
- `xledgermate-alpha.service` — `python -m alpha run`
- `xledgermate-alpha-gui.service` — Streamlit on `:8503`

Deploy: `scripts/vps_deploy_alpha.sh` (branch `alpha`).

See [ALPHA_MAINNET_CUTOVER.md](ALPHA_MAINNET_CUTOVER.md) for go-live checklist.
