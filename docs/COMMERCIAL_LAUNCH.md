# Open Desk — Commercial SaaS launch plan

**Branch:** `open-desk`  
**Product version start:** `2.4.0`  
**Positioning:** *Bring your keys — we run the desk.*

Hosted xLedgerMate for subscribers: same engine/TA stack, multi-user accounts, per-user wallets and integrations, subscription billing. Not a new strategy codebase.

---

## Current foundation (already shipped)

| Asset | Role |
|-------|------|
| Engine + TA + risk | Shared market brain |
| Alpha HUD + Config tab | Operator surface (to evolve into subscriber + admin) |
| HTTPS `xledgermate.com` | Public front door (Caddy) |
| HUD login (Config-tab reloadable) | Single-operator auth → precursor to multi-user |
| Per-integration patterns | Wallet, Telegram, Grok-ready Config fields |

---

## Locked architecture

```text
Browser → Auth → tenant_id
                 → integrations (wallet, grok, telegram, onramp)
                 → risk / dry_run / kill / bag / fills
              → Shared market snapshot (book, TA, regime)
              → Executor: for each active paid tenant → size + sign on *their* wallet
```

| Shared | Per subscriber |
|--------|----------------|
| Strategy/TA code, book feed | Login, plan, entitlements |
| Market snapshot | Encrypted wallet + Grok + Telegram |
| Domain / hosting | Bag, fills, guidance, kill switch |

**Do not:** clone full engine process per user, or pool capital in one house wallet for v1.

---

## Phases

### Phase 0 — Product freeze
- Go-live checklist (required vs optional integrations)
- Tenant schema draft
- Plan matrix (Trial / Pro / Live)
- Admin vs subscriber HUD map
- Legal one-pager (self-custody software; not a fund)
- **Foolproof onboarding** — see [`ONBOARDING_FOOLPROOF.md`](./ONBOARDING_FOOLPROOF.md)  
  (Xaman cold · Kraken on-ramp · bot wallet · RLUSD trustline · referral links)

### Phase 1 — Real accounts
- Users table, signup/login (email + password)
- Sessions; replace single global `XLG_HUD_*` as product login
- Platform-admin escape hatch for operator
- Soft multi-tenant HUD shell

### Phase 2 — Per-user integrations
- Namespace Config: wallet, Grok, Telegram, onramp prefs per `user_id`
- Encrypted secrets at rest
- Onboarding checklist UI (no raw `.env` for customers)

### Phase 3 — Multi-tenant execution
- Single `MarketSnapshot` publisher
- Tenant executor loop (active + paid + not killed)
- Per-user risk capital / dry_run
- Isolation tests (A never sees or signs B)

### Phase 4 — Billing
- Stripe checkout + portal
- Plans → entitlements (`can_run_engine`, `live_enabled`, caps)
- Webhooks: activate / past_due / cancel → pause tenant

### Phase 5 — Subscriber HUD
- Default: Home, Activity, Setup, Account
- Advanced knobs / quant panels behind Advanced or Admin only

### Phase 6 — Hardening
- KMS/app-key encryption, rate limits, audit log, backups
- Optional Cloudflare proxy/WAF
- Per-tenant error isolation

---

## Build order

1. Phase 0 artifacts (approve)  
2. Phase 1 auth  
3. Phase 2 secrets + onboarding  
4. Phase 3 multi-wallet execute  
5. Phase 4 Stripe  
6. Phase 5 UX skin  

---

## Open decisions (lock in Phase 0)

1. Trial: dry-run only vs live with tiny caps?  
2. Grok required or optional in v1?  
3. Telegram required for alerts?  
4. Custody: encrypted bot secret stored by platform vs re-paste only?  
5. Pricing ballpark for Pro paper vs Live?

---

## Branch policy

- **Base:** cut from `samurai` (operator Alpha line)  
- **This branch:** `open-desk` — all commercial/SaaS work lands here first  
- **VERSION:** starts at `2.4.0`; bump per milestone  
- Merge to mainline only after Phase N exit criteria agreed  

---

*Last updated: 2026-07-30 — commercial launch kickoff*
