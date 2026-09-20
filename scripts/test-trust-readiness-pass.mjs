import fs from "node:fs";
import assert from "node:assert/strict";

const read=p=>fs.readFileSync(p,"utf8");

const network=read("public/downloads/index.html");
const portal=read("public/quantic.js");
assert.ok(network.includes("data-status-meta"),"Network must display verification metadata");
assert.ok(network.includes("data-network-refresh"),"Network must offer manual refresh");
assert.ok(portal.includes("performance.now"),"Network status must measure request latency");
assert.ok(portal.includes("Dernière vérification"),"Network must timestamp checks");
assert.ok(portal.includes("setInterval"),"Network must refresh automatically");

const mail=read("public/mail/index.html");
assert.ok(mail.includes("Quantic ID requis"),"Mail static fallback must explain Quantic ID immediately");
assert.ok(mail.includes("/downloads/#identity-vault"),"Mail static fallback must link Identity Vault");
assert.ok(mail.includes("Réessayer"),"Mail static fallback must expose retry");
const mailSync=read("scripts/sync-quantic-mail.mjs");
assert.ok(mailSync.includes("Quantic ID requis."),"Mail sync must preserve explicit Quantic ID fallback");
assert.ok(mailSync.includes("data-qm-static-actions"),"Mail sync must preserve immediate recovery actions");

const qid=read("public/quantic/index.html");
assert.ok(qid.includes('q-card-logo-wrap'),"Quantic ID cards must use product logo containers");
assert.ok(qid.includes('/assets/brand-2026/vision-mark.svg'),"Quantic ID Vision card must use the Vision logo");
assert.ok(qid.includes('/assets/brand-2026/mail-mark.svg'),"Quantic ID Mail card must use the Mail logo");
assert.ok(!qid.includes('<span class="q-card-icon">V</span>'),"Quantic ID must not concatenate icon letters into readable text");
assert.ok(!qid.includes('<span class="q-card-icon">M</span>'),"Quantic ID must not concatenate icon letters into readable text");
assert.ok(qid.includes("Quantic ID est la clé"),"Quantic ID positioning must be explicit");

const pulse=read("public/pulse/index.html");
const pulseSession=read("public/pulse/session.js");
assert.ok(pulse.includes("Entrer avec Quantic ID"),"Pulse public UX must use Quantic ID language");
assert.ok(pulse.includes("Créer avec Quantic ID"),"Pulse registration must use Quantic ID language");
assert.ok(!/mot de passe/i.test(pulseSession),"Pulse session UX must not reintroduce passwords");

const track=read("public/track-record/index.html");
const trackJs=read("public/track-record/track-record.js");
assert.ok(track.includes("Ce qu’il faut avant de publier un score"),"Track Record must explain evidence threshold");
assert.ok(track.includes("data-track-threshold-progress"),"Track Record needs a measurable evidence progress surface");
assert.ok(trackJs.includes("data-track-threshold-progress"),"Track Record runtime must update evidence progress");
assert.ok(trackJs.includes("minimum_global_samples"),"Track Record must use real threshold data");

const downloads=read("public/downloads/index.html");
assert.ok(downloads.includes("Sécurité des téléchargements"),"Downloads must explain distribution trust");
assert.ok(downloads.includes("Signature Windows"),"Downloads must expose signing status");

console.log(JSON.stringify({ok:true,contract:"trust-readiness-pass"}));
