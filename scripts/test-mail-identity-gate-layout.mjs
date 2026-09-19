import fs from "node:fs";
import assert from "node:assert/strict";

const gate=fs.readFileSync("public/quantic-mail-id-gate.js","utf8");

assert.ok(gate.includes("position:fixed"),"gate must be fixed to the viewport");
assert.ok(gate.includes("inset:0"),"gate must cover all viewport edges");
assert.ok(gate.includes("z-index:2147483647"),"gate must sit above the Mail app");
assert.ok(gate.includes("height:100dvh"),"gate must use dynamic viewport height");
assert.ok(gate.includes("shieldBackground"),"gate must isolate the Mail DOM behind it");
assert.ok(gate.includes("MutationObserver"),"gate must isolate nodes added during Next hydration");
assert.ok(gate.includes(".inert=true"),"background nodes must become inert while locked");
assert.ok(gate.includes("restoreBackground"),"unlock must restore the Mail DOM");

console.log(JSON.stringify({ok:true,contract:"mail-identity-gate-fullscreen"}));
