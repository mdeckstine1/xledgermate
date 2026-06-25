# E2 — Branch discipline (Samurai · Alpha · legacy WS)

**Status:** **`samurai-v1.0.1`** = frozen VPS production pin (v1.0.1) · **`samurai`** = active Samurai feature development · **`alpha`** = solid baseline (parallel line, no Samurai feature work)

---

## Samurai frozen-release workflow

```text
samurai-v1.0.1   ← frozen release (deploy VPS; hotfixes only → cut samurai-v1.0.2)
       │
       └── samurai   ← daily work in Cursor (new features for next Samurai release)
       
alpha            ← separate line; stable; do not mix Samurai feature commits here
```

| Step | Action |
|------|--------|
| **Daily dev** | Commit on **`samurai`** |
| **VPS production** | Deploy **`samurai-v1.0.1`** (or latest `samurai-v1.0.x` tag) — `ALPHA_BRANCH=samurai-v1.0.1 bash scripts/vps_deploy_alpha.sh` |
| **Cut patch release** | From tested `samurai` → tag/branch `samurai-v1.0.2`, deploy, leave pin frozen |
| **Avoid** | Feature commits directly on `samurai-v1.0.x` pins or on `alpha` when the work is Samurai-only |

**Checkout tip:** branch and tag share names like `samurai-v1.0.1` — use `git checkout refs/heads/samurai-v1.0.1` for the frozen branch (not ambiguous with the tag).

---

## Which branch for what

| Branch | Deploy to VPS live? | Role |
|--------|---------------------|------|
| **`samurai`** | No (dev) | **Active Samurai development** — feature work in Cursor |
| **`samurai-v1.0.1`** | **Yes (production pin)** | Frozen v1.0.1 — reproducible mainnet deploy only |
| **`alpha`** | Optional | Trading Bot Alpha baseline (solid); parallel line, not Samurai features |
| **`samurai-v1.0.0`** | No (legacy MM) | Pre-Alpha MM line — superseded |
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

**VPS production (Samurai pin — frozen release):**

```bash
cd /root/xledgermate
ALPHA_BRANCH=samurai-v1.0.1 bash scripts/vps_deploy_alpha.sh
```

**VPS soak (Samurai dev branch — only when testing features):**

```bash
ALPHA_BRANCH=samurai bash scripts/vps_deploy_alpha.sh
```

**Legacy Alpha line (optional):**

```bash
ALPHA_BRANCH=alpha bash scripts/vps_deploy_alpha.sh
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
