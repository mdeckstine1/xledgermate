# E2 — Branch discipline (Alpha vs legacy WS + pure A-S)

**Status:** **`alpha`** = primary production (Trading Bot Alpha v1.0.0) · **`Ashigaru-Shoshin`** = archived MM rollback (v2.3.x)

---

## Which branch for what

| Branch | Deploy to VPS live? | Role |
|--------|---------------------|------|
| **`alpha`** | **Yes (primary)** | Trading Bot Alpha: value accumulation, brackets, `python -m alpha run` |
| **`Ashigaru-Shoshin`** | Rollback only | Legacy MM: QD stack, `ws-engine`, HUD `:8765` |
| **`Ashigaru-Kaizen-II`** | No (archived) | v2.1.40 — historical |
| **`Ashigaru-Kaizen`** | No (archived) | v2.1.10 era — historical |
| **`grok-tier-2-collab`** | No | Sacred Gate 2 replay corpus |

**Cutover:** [`ALPHA_HANDOVER.md`](ALPHA_HANDOVER.md) · **Legacy sunset:** [`LEGACY_MM_SUNSET.md`](LEGACY_MM_SUNSET.md)

---

## Two bots, one repo

| Bot | Command / service | Use |
|-----|-------------------|-----|
| **Trading Bot Alpha** | `python -m alpha run` · `xledgermate-alpha` | **Primary production** |
| **Legacy WS MM** | `python main.py --mode ws-engine` · `xledgermate` | **Rollback / archive only** |

**Rule:** Do not run both live on the same Bot Account.

---

## Operator commands

**VPS production (Alpha — primary):**

```bash
cd /root/xledgermate
bash scripts/alpha_cutover_vps.sh    # first time
bash scripts/vps_deploy_alpha.sh     # updates
python -m alpha status
```

**VPS rollback (legacy MM):**

```bash
bash scripts/alpha_rollback_to_legacy.sh
```

**Sacred replay / economics (dev machines only):**

```powershell
python -m experimental.grokster
python -m experimental.ws_feed.replay_long_run --as-mode pure --economics
```

---

## Related

- [`ALPHA_HANDOVER.md`](ALPHA_HANDOVER.md) — operator handover (go-live)
- [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) — daily ops
- [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) — legacy MM checklist
- [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) — legacy WS + pure A-S (archive)
