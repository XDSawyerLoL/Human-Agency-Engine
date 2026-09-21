import fs from "node:fs";
import assert from "node:assert/strict";

const sync=fs.readFileSync("scripts/sync-quantic-mail.mjs","utf8");
assert.match(sync,/XDSawyerLoL\/QuanticMail/);
assert.match(sync,/5891f79e3f7c0e70678eb8a50d925a32d61c4420/);
assert.match(sync,/46794c67ec5729cb368b390f0690c2cf220f7016/);
assert.match(sync,/quantic-hostinger-relay\.invalid/);
assert.match(sync,/QUANTICMAIL_COMMIT/);
assert.match(sync,/QUANTIC_HOSTINGER_RELAY_URL/);
assert.match(sync,/patchSentinel/);
assert.match(sync,/injectPortalNav/);
assert.match(sync,/injectIdentityGate/);
assert.match(sync,/makePortalUrlsPortable/);
assert.match(sync,/injectMailResilience/);
assert.match(sync,/quantic-mail-resilience\.js/);
assert.match(sync,/LEGACY_PORTAL_ORIGIN/);
assert.match(sync,/quantic-mail-portal-nav\.js/);
assert.match(sync,/public[\\/]mail|public",\s*"mail"/);
assert.doesNotMatch(sync,/npm",\["install/);
assert.doesNotMatch(sync,/build:hostinger/);

const pkg=JSON.parse(fs.readFileSync("package.json","utf8"));
assert.match(pkg.scripts.build,/sync-quantic-mail\.mjs/);

const nodeStatus=fs.readFileSync("src/quantic_portal_status.js","utf8");
assert.match(nodeStatus,/id:'mail'.*public_url:'\/mail\/'/s);
assert.doesNotMatch(nodeStatus,/id:'mail'.*quanticmail\.onrender\.com/s);

const pyStatus=fs.readFileSync("app/quantic_portal_status.py","utf8");
assert.match(pyStatus,/id="mail"[\s\S]*public_url="\/mail\/"/);
assert.doesNotMatch(pyStatus,/id="mail"[\s\S]*quanticmail\.onrender\.com/);

console.log(JSON.stringify({ok:true,contract:"hostinger-native-quanticmail-v3-prebuilt"}));
