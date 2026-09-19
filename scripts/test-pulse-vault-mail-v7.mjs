import fs from "node:fs";
import assert from "node:assert/strict";

const pulseHtml=fs.readFileSync("public/pulse/index.html","utf8");
const pulseApp=fs.readFileSync("public/pulse/app.js","utf8");
const pulseSession=fs.readFileSync("public/pulse/session.js","utf8");
const pulseBackend=fs.readFileSync("src/quantic_pulse.js","utf8");
const idRuntime=fs.readFileSync("public/quantic-id-runtime.js","utf8");

assert.ok(pulseHtml.includes('/quantic-id-runtime.js'),"Pulse must load Quantic ID runtime");
assert.ok(pulseHtml.includes('data-pulse-id-status'),"Pulse auth modal must display Identity Vault status");
assert.ok(pulseApp.includes('/api/pulse/auth/challenge'),"Pulse must request a server challenge");
assert.ok(pulseApp.includes('QuanticID.assert'),"Pulse must obtain an Identity Vault signature");
assert.ok(pulseSession.includes('QuanticID.probe'),"Pulse must refuse auth UI when Vault is unavailable");

for(const marker of [
  "/api/pulse/auth/challenge",
  "verifyIdentityProof",
  "identityKeyId",
  "identityPublicKey",
  "identity_proof_required",
  "identity_mismatch"
]) assert.ok(pulseBackend.includes(marker),marker);

assert.ok(idRuntime.includes("ASSERT_URL"),"Quantic ID runtime must expose assertion endpoint");
assert.ok(idRuntime.includes("async function assert"),"Quantic ID runtime must sign challenges");
assert.ok(idRuntime.includes("/v1/assert"),"Quantic ID runtime must call Identity Vault assertion endpoint");

assert.ok(fs.existsSync("public/quantic-mail-v7.css"),"Mail V7 stylesheet must exist");
const mailCss=fs.readFileSync("public/quantic-mail-v7.css","utf8");
for(const marker of [
  ".qn-mail-app",
  ".qm-header",
  ".qm-shell",
  ".qm-drawer",
  ".qm-list-panel",
  ".qm-message-row",
  ".qm-reader",
  ".qm-compose-sheet",
  ".qm-bottom-nav"
]) assert.ok(mailCss.includes(marker),marker);

const mailNav=fs.readFileSync("public/quantic-mail-portal-nav.js","utf8");
assert.ok(mailNav.includes("quantic-mail-v7.css"),"Mail portal navigation must inject V7 stylesheet");

const sync=fs.readFileSync("scripts/sync-quantic-mail.mjs","utf8");
assert.ok(sync.includes("quantic-mail-v7.css"),"Mail sync must preserve V7 across exported pages");

console.log(JSON.stringify({ok:true,contract:"pulse-vault-auth-mail-v7"}));
