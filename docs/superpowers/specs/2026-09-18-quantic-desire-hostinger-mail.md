# Quantic Desire UI + Hostinger Mail migration

## Visual direction
Quantic uses a premium dark visual system: deep graphite, cold blue, restrained violet, dense glass, orbital light, large editorial typography and deliberate whitespace.

## UX goals
- immediate hierarchy in the first viewport;
- one coherent shell across Portal, Centre, Mail, Network and Products;
- richer depth without visual noise;
- motion only when it reinforces hierarchy;
- keyboard and reduced-motion accessibility;
- no fabricated metrics or availability claims.

## Interaction model
- subtle pointer spotlight and card tilt on fine-pointer devices;
- scroll reveal through IntersectionObserver;
- all navigation remains standard anchor navigation without JavaScript;
- status behavior remains independent of visual motion.

## Mail migration boundary
Quantic Mail web and relay are separate deployment units. Render is not removed until a Hostinger-hosted web application and a Hostinger-hosted relay have passed production smoke tests. The portal may prefer Hostinger only after those checks.
