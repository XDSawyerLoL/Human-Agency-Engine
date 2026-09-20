# Quantic Sillage — Audit remediation 2026-09-21

This file tracks the engineering response to the independent product/commercial audit dated 2026-09-20.

## Release rule

Do not present the platform as production-ready while a P0 is open or while a P1 affecting confidentiality, durable data, identity presence, forecast integrity, or service-health truthfulness remains unresolved.

## Implemented in PR #126

| Audit item | Engineering response | Regression evidence |
| --- | --- | --- |
| A01 · P0 | Centralized Pulse visibility is now re-applied to nested quotes, reactions, bookmarks, replies and quote creation. Private references cannot be promoted into a public post. | `scripts/test-audit-remediation.mjs` |
| A02 · P1 | Quantic ID now combines the long session cookie with a short server-side presence lease renewed only by a fresh Vault signature. | `scripts/test-audit-remediation.mjs` |
| A04 · P1 | Health now distinguishes network reachability from a functional service. Protected web apps are checked through their Quantic ID redirect contract; relays must return the relay health schema. | `scripts/test-quantic-portal-status.mjs` |
| A05 · P1 | A stable scenario key keeps the first published target deadline in memory, MySQL and learning metadata. | `scripts/test-audit-remediation.mjs` |
| A06 · P1 | Calibration readiness requires sample volume plus Brier/ECE/Brier-skill quality thresholds. | `scripts/test-audit-remediation.mjs` |
| A07 · P1 | Production smoke no longer follows private redirects and pretends to test authenticated pages. It explicitly validates the 302 Quantic ID guard. | Hostinger production smoke workflow |
| A12 · P2 partial | Direct Node dependencies are pinned exactly. | `package.json` |

## Still operationally blocking

The code cannot turn an absent production database or relay credential into durable infrastructure. Before merging for production, Hostinger must expose working persistent storage and a functional embedded relay. `/api/health` now reports `degraded` and `ready_for_production:false` when persistence is absent.

A complete `package-lock.json` is also still required before the dependency-reproducibility item is considered closed. Exact direct dependency pins reduce drift but do not replace a lockfile.

## Still product/commercial work

The audit's distribution-signing, macOS/Linux/mobile support, legal/privacy/support surfaces, moderation operations, recovery procedures, Mail hydration issue, News differentiation, social traction and market-validation requirements remain separate workstreams. They must not be marked resolved by this security PR.

## Acceptance sequence

1. CI and audit regression tests green.
2. No Pulse authorization bypass in the role matrix.
3. Presence lease expires and revokes protected API access without a new Vault proof.
4. Same scenario key retains the same first target deadline.
5. Thirty deliberately wrong forecasts never produce `calibration_ready:true`.
6. Production health reports durable storage and all required relay checks functional.
7. Hostinger production smoke green.
8. Only then consider a limited pilot; commercial launch remains a separate decision.
