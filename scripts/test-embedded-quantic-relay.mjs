import fs from "node:fs";
import assert from "node:assert/strict";

const sync=fs.readFileSync("scripts/sync-quantic-mail.mjs","utf8");
assert.match(sync,/fc1bafe8ea3da99f0f4218e23b4b34d882005f84/);
assert.match(sync,/standalone-relay/);
assert.match(sync,/lib/);
assert.match(sync,/vendor[\\/]quanticmail-relay|vendor",\s*"quanticmail-relay"/);

const server=fs.readFileSync("server_core.js","utf8");
assert.match(server,/installEmbeddedQuanticRelay/);
assert.ok(server.indexOf("installEmbeddedQuanticRelay(app)") < server.indexOf("express.json"),"relay must mount before express.json");

const embedded=fs.readFileSync("src/quantic_embedded_relay.js","utf8");
assert.match(embedded,/createMySqlRelayPersistenceFromConfig/);
assert.match(embedded,/createEmbeddedRelay/);
assert.match(embedded,/mediumorchid-badger-314305\.hostingersite\.com/);
assert.match(embedded,/QUANTIC_RELAY_IDENTITY_SECRET|sha256/i);
assert.match(embedded,/quanticmail-network-relay\.onrender\.com/);
assert.match(embedded,/quantic-network-relay-backup-production\.up\.railway\.app/);

const pkg=JSON.parse(fs.readFileSync("package.json","utf8"));
assert.match(pkg.scripts.start,/experimental-transform-types/);

console.log(JSON.stringify({ok:true,contract:"embedded-hostinger-relay"}));
