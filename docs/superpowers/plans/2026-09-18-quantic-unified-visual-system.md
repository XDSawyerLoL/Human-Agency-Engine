# Quantic Unified Visual System — Implementation Plan

## Task 1 — Visual contract tests (RED)
- Extend `tests/test_quantic_portal.py` to require `quantic-unified.css` on Portal, Centre, Vision, Network, Products.
- Add checks that Vision internal shell script contains `q-global-nav` and `q-vision-subnav`, and does not inject `p15-sidebar` or `p15-topbar`.
- Add Node smoke test for shell HTML injection contract.
- Run CI and confirm failures are due to missing unified layer.

## Task 2 — Shared design system (GREEN)
- Add `public/quantic-unified.css`.
- Define common tokens, star/aurora background, navigation, hero, glass panels, buttons, typography, mobile rules and reduced-motion behavior.
- Load after existing CSS to normalize without breaking Providence internals.

## Task 3 — Global Providence shell (GREEN)
- Rewrite `public/providence-v15-shell.js` navigation injection.
- Replace fixed sidebar/topbar with global Quantic nav and Vision subnav.
- Keep mobile navigation behavior compact and consistent.
- Preserve all page IDs and existing scripts.

## Task 4 — Portal + Vision alignment
- Update root, Centre, Network, Products and Vision home to load unified CSS.
- Rework root/section composition where needed to use Providence-inspired color richness.
- Remove one-off Vision top navigation.

## Task 5 — Cross-page normalization
- Add CSS overrides for prediction hero, analyst, alerts, track record and generic Providence panels.
- Verify no page retains left-offset layout or fixed sidebar spacing.

## Task 6 — Verification and production
- Run full Node and Python CI.
- Merge only on green.
- Verify production via Hostinger smoke runner.
- Then resume native QuanticMail Hostinger integration on top of the unified visual base.
