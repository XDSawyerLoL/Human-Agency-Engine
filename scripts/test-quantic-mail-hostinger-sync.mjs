import fs from "node:fs";
import assert from "node:assert/strict";

const script=fs.readFileSync("scripts/sync-quantic-mail.mjs","utf8");
assert.match(script,/d1e1ad51a8686c30677666c659952b4d72cc7491/);
assert.match(script,/XDSawyerLoL\/QuanticMail/);
assert.match(script,/build:hostinger/);
assert.match(script,/NEXT_PUBLIC_QUANTIC_BOOTSTRAPS/);
assert.match(script,/quantic-network-relay-backup-production\.up\.railway\.app/);
assert.match(script,/public[\\/]mail|public",\s*"mail"/);

const pkg=JSON.parse(fs.readFileSync("package.json","utf8"));
assert.match(pkg.scripts.build,/sync-quantic-mail\.mjs/);

console.log(JSON.stringify({ok:true,contract:"hostinger-native-quanticmail"}));
