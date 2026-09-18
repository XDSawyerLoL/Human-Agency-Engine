import fs from "node:fs";
import assert from "node:assert/strict";

const sync=fs.readFileSync("scripts/sync-quantic-mail.mjs","utf8");
assert.match(sync,/XDSawyerLoL\/QuanticMail/);
assert.match(sync,/85641d971163416225ffc386468951832782c227/);
assert.match(sync,/build:hostinger/);
assert.match(sync,/public[\\/]mail|public",\s*"mail"/);
assert.match(sync,/QUANTIC_HOSTINGER_RELAY_URL/);
assert.match(sync,/mailBootstraps/);

const pkg=JSON.parse(fs.readFileSync("package.json","utf8"));
assert.match(pkg.scripts.build,/sync-quantic-mail\.mjs/);

const nodeStatus=fs.readFileSync("src/quantic_portal_status.js","utf8");
assert.match(nodeStatus,/id:'mail'.*public_url:'\/mail\/'/s);
assert.doesNotMatch(nodeStatus,/id:'mail'.*quanticmail\.onrender\.com/s);

const pyStatus=fs.readFileSync("app/quantic_portal_status.py","utf8");
assert.match(pyStatus,/id="mail"[\s\S]*public_url="\/mail\/"/);
assert.doesNotMatch(pyStatus,/id="mail"[\s\S]*quanticmail\.onrender\.com/);

console.log(JSON.stringify({ok:true,contract:"hostinger-native-quanticmail-v3"}));
