import assert from "node:assert/strict";
import { quanticServiceTargets } from "../src/quantic_portal_status.js";

const pending=quanticServiceTargets({});
const pendingRelay=pending.find(x=>x.id==="relay-hostinger");
assert.equal(pendingRelay.state,"pending");
assert.equal(pendingRelay.probe_url,null);

const active=quanticServiceTargets({QUANTIC_HOSTINGER_RELAY_URL:"https://relay-hostinger.example.com/"});
const relay=active.find(x=>x.id==="relay-hostinger");
assert.equal(relay.state,"active");
assert.equal(relay.public_url,"https://relay-hostinger.example.com");
assert.equal(relay.probe_url,"https://relay-hostinger.example.com/api/quantic/health");

const invalid=quanticServiceTargets({QUANTIC_HOSTINGER_RELAY_URL:"http://relay-hostinger.example.com"});
assert.equal(invalid.find(x=>x.id==="relay-hostinger").state,"pending");

console.log(JSON.stringify({ok:true,contract:"hostinger-relay-activation"}));
