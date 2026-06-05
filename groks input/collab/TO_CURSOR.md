# To Cursor — from Grok / operator

*Cursor: read this file when picking up work. Latest entry at top.*

---

## 2026-06-05 — Active thread

**Operator context**
- Gate 2 pilot on VPS `188.245.50.229`, engine via `systemd` (`xledgermate`).
- Do **not** use Full GUI Start/Restart on VPS — use `clear-kill` + `systemctl restart`.
- Telegram: kill alerts + **hourly report** (`xledgermate-hourly-report.timer`) — working.
- VPS `config.yaml` session kill updated to **0.85 / 45 fills** (was 0.35/25).

**Open asks for Cursor (if/when coding)**
1. **GUI cleanup** — operator mode for VPS (hide Start/Restart), Gate 2 single-page desk; see operator chat 2026-06-05.
2. **Telegram** — optional `/status` and guarded `/clear_kill` (spread/RPC only)? Operator wanted remote ops without SSH.
3. **BookOffers / Tier 2.5** — per `docs/05` when Gate 2 data justifies it.

**Grok left on VPS (not necessarily in git yet)**
- `scripts/hourly_telegram_report.py` + timer installed.
- `groks-input-vps-install-hourly.sh` on server (copy of install script).

*Reply in [FROM_CURSOR.md](FROM_CURSOR.md).*

**Collab protocol:** Grok writes here → Cursor reads here first. Cursor replies in `FROM_CURSOR.md`. Operator priorities in `OPERATOR_NOTES.md`. Milestones still go to [FOR_AI_AND_FUTURE_SESSIONS.md](../FOR_AI_AND_FUTURE_SESSIONS.md).

---

## Archive

*(older entries)*