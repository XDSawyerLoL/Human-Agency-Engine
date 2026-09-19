import fs from "node:fs";
import assert from "node:assert/strict";

const read=p=>fs.readFileSync(p,"utf8");
const network=read("public/network/index.html");\nconst downloads=read("public/downloads/index.html");
const quantic=read("public/quantic.js");
const mail=read("public/mail/index.html");
const mailResilience=read("public/quantic-mail-resilience.js");
const predictions=read("public/predictions/predictions-v16-15.js");
const track=read("public/track-record/track-record.js");
const visionHome=read("public/quantic-vision-home-v8.js");
const products=read("public/products/index.html");
const home=read("public/index.html");

assert.ok(!network.includes("État du réseau inconnu"),"Network must not expose unknown status copy");
assert.ok(network.includes('class="q-technical-details"'),"Network must move provider details behind a technical disclosure");
assert.ok(network.includes("Si un chemin tombe, Quantic cherche un autre chemin disponible."),"Network must lead with user-facing resilience language");
assert.ok(network.includes("data-network-continuity"),"Network must expose an aggregate continuity state");

assert.ok(quantic.includes("STATUS_TIMEOUT_MS"),"Network status fetch must have an explicit timeout");
assert.ok(quantic.includes("AbortController"),"Network status fetch must be abortable");
assert.ok(quantic.includes("Monitoring indisponible"),"Network status failure must be explicit");
assert.ok(quantic.includes('unknown: "Non vérifié"'),"Unknown service state must be phrased as non-verified");
assert.ok(!quantic.includes("État du réseau inconnu"),"Status runtime must not use vague unknown wording");

assert.ok(!mail.includes("mediumorchid-badger-314305.hostingersite.com"),"Mail navigation must be domain-portable");
assert.ok(mail.includes("/quantic-mail-resilience.js"),"Mail must load stuck-manifest recovery");
assert.ok(mailResilience.includes("Vérification plus longue que prévu"),"Mail must explain a stuck manifest");
assert.ok(mailResilience.includes("Réessayer"),"Mail must expose retry");

assert.ok(predictions.includes("SNAPSHOT_TIMEOUT_MS"),"Predictions must have a timeout");
assert.ok(predictions.includes("AbortController"),"Predictions fetch must be abortable");
assert.ok(predictions.includes("data-p1615-retry"),"Predictions must expose retry on failure");

assert.ok(track.includes("TRACK_TIMEOUT_MS"),"Track record must have a timeout");
assert.ok(track.includes("AbortController"),"Track record fetch must be abortable");
assert.ok(track.includes("data-track-retry"),"Track record must expose retry on failure");

assert.ok(visionHome.includes("VISION_TIMEOUT_MS"),"Vision home must have a timeout");
assert.ok(visionHome.includes("AbortController"),"Vision home fetch must be abortable");
assert.ok(visionHome.includes("data-qv8-retry"),"Vision home must expose retry on failure");

assert.ok(!products.includes("stockage MySQL Hostinger"),"Products page must not lead with infrastructure implementation");
assert.ok(products.includes("La couche sociale native de Quantic"),"Pulse positioning must be ecosystem-first");
assert.ok(products.includes("plusieurs chemins de continuité"),"Network positioning must be benefit-led");
assert.ok(home.includes("continuer à fonctionner si un chemin devient indisponible"),"Home Network card must explain the benefit");

console.log(JSON.stringify({ok:true,contract:"market-readiness-pass"}));
