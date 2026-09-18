# Quantic Unified Visual System — Design

## Goal
Make every public Quantic surface feel like one product family. Providence/Quantic Vision is the visual source of truth: deep navy, electric blue, cyan, violet, restrained gold, stars, orbit/temporal motifs, luminous glass and cinematic spacing.

## Non-negotiables
- One global Quantic navigation language across Portal, Centre, Vision, Mail, Network, Products and Providence-derived pages.
- Remove the desktop-software feeling from Providence internal pages: no fixed left sidebar, no dense admin-console topbar.
- Preserve all existing Providence data surfaces, IDs, runtime hooks and business behavior.
- Keep page-specific color identity subtle; shared geometry, typography and navigation must dominate.
- Mobile uses a compact Quantic dock/drawer, not a shrunken desktop sidebar.
- Motion must respect prefers-reduced-motion.

## Architecture
1. Create a shared global visual layer: `public/quantic-unified.css`.
2. Portal surfaces load that layer after their existing CSS.
3. Providence pages load the same layer last, so it overrides legacy shell geometry without deleting functional styles.
4. Rewrite `providence-v15-shell.js` so it injects a Quantic top navigation + compact Vision subnav instead of `.p15-sidebar` + `.p15-topbar`.
5. Update Vision home to use the same global shell.
6. Keep page internals (prediction cards, analyst chat, alerts, track record, sports, etc.) intact but visually normalized through the shared tokens and wrapper styles.

## Shared visual language
- Background: #02050b / #020713
- Electric blue: #148cff
- Cyan: #20d8ff
- Violet: #9b5cff
- Gold: #ffc74d
- Text: #f7fbff
- Muted: #8ea5bd
- Panels: translucent blue-black glass, 14–22px radius
- Hero atmosphere: star field + radial light + orbital / temporal cues
- Navigation: floating translucent top shell with Quantic brand, product tabs, and Vision subnav when relevant.

## Page treatment
### Portal / Centre / Products / Network
Use cinematic Providence color and atmosphere. Reduce generic SaaS card appearance; increase editorial rhythm, asymmetry and visual storytelling.

### Vision home
Keep timeline/orbit richness. Replace its one-off top navigation with the global Quantic shell.

### Providence-derived internal pages
Predictions, Analyst, Alerts, Track Record, Sports, Sources, Backtest, Cameras, Settings:
- remove fixed sidebar and console topbar;
- inject common global Quantic navigation;
- inject compact horizontal Vision section nav;
- center content within max-width shell;
- retain page-specific content and data IDs;
- use shared visual tokens to normalize panels, buttons, badges and headers.

### Mail
Mail inherits the same tokens during Hostinger export. No iframe-style visual break once native Hostinger Mail is activated.

## Testing
- Contract test verifies every primary public surface loads the unified stylesheet.
- Contract test verifies Providence shell no longer injects `.p15-sidebar` or `.p15-topbar`.
- Contract test verifies global shell markers are present.
- Existing Providence runtime tests must remain green.
- Production smoke verifies homepage, Vision, Network and Mail route signatures after deploy.
