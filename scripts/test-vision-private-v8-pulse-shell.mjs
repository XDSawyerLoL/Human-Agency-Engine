import fs from "node:fs";
import assert from "node:assert/strict";

const server=fs.readFileSync("server_core.js","utf8");
const identity=fs.readFileSync("src/quantic_identity.js","utf8");
const idPage=fs.readFileSync("public/quantic-id-page.js","utf8");
const vision=fs.readFileSync("public/vision/index.html","utf8");
const pulse=fs.readFileSync("public/pulse/index.html","utf8");
const pulseCss=fs.readFileSync("public/pulse/pulse.css","utf8");

assert.ok(server.includes("installQuanticIdentity(app)"),"server must install Quantic ID endpoints");
assert.ok(server.includes("requireQuanticIdentity"),"server must enforce Quantic ID");
assert.ok(server.indexOf("requireQuanticIdentity")<server.indexOf("express.static"),"Vision access control must execute before static files");

for(const marker of [
  "/api/id/challenge",
  "/api/id/session",
  "quantic_id_session",
  "verifyIdentityProof",
  "HttpOnly",
  "SameSite=Lax",
  "quantic-sillage"
]) assert.ok(identity.includes(marker),marker);

for(const route of ["/vision","/predictions","/analyst","/alerts","/sports","/cameras","/track-record","/sources","/backtest","/settings","/causal","/crypto","/horizons","/intelligence","/matches","/modules"]){
  assert.ok(identity.includes(route),route+" must be private");
}
assert.ok(identity.includes("pathname.startsWith('/api/')"),"Providence APIs must be private");
assert.ok(identity.includes("res.status(401)"),"private API must reject unauthenticated requests");
assert.ok(identity.includes("res.redirect"),"private pages must redirect to Quantic ID");

assert.ok(idPage.includes("/api/id/challenge"),"Quantic ID page must request a server challenge");
assert.ok(idPage.includes("/api/id/session"),"Quantic ID page must establish server session");
assert.ok(idPage.includes("QuanticID.assert"),"Identity Vault must sign the server challenge");

assert.ok(vision.includes("qv8-hero"),"Vision home must use native V8 markup");
assert.ok(vision.includes("qv8-workspace"),"Vision home must use native product workspace");
assert.ok(!vision.includes("providence-home-v16-11.css"),"Vision home must not depend on legacy home CSS");
assert.ok(!vision.includes("providence-future-v17.css"),"Vision home must not depend on legacy future CSS");
assert.ok(!vision.includes("quantic-vision-v7.css"),"Vision home must not be a V7 overlay");

assert.ok(pulse.includes("q-sillage-global"),"Pulse must keep the global Sillage menu");
assert.ok(pulse.includes("pulse-shell"),"Pulse local navigation must remain");
assert.ok(pulseCss.includes(".q-sillage-global"),"Pulse CSS must account for the global menu");
assert.ok(pulseCss.includes("top:64px"),"Pulse local sidebar must sit below global navigation");

console.log(JSON.stringify({ok:true,contract:"vision-private-native-v8-pulse-global-shell"}));
