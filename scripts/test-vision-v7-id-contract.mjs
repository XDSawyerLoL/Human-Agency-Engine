import fs from "node:fs";
import assert from "node:assert/strict";

const routes=[
  "vision","predictions","analyst","alerts","sports","cameras",
  "track-record","sources","backtest","settings","causal","crypto",
  "horizons","intelligence","matches","modules"
];

for(const route of routes){
  const path=`public/${route}/index.html`;
  assert.ok(fs.existsSync(path),path);
  const html=fs.readFileSync(path,"utf8");
  assert.ok(html.includes("/quantic-id-runtime.js"),route+" must load Quantic ID runtime");
  assert.ok(html.includes("/quantic-vision-id-gate.js"),route+" must load Quantic Vision gate");
  if(route==="vision"){
    assert.ok(html.includes("/quantic-vision-home-v8.css"),"Vision home must load native V8 CSS");
    assert.ok(!html.includes("/quantic-vision-v7.css"),"Vision home must not load legacy overlay CSS");
  }else{
    assert.ok(html.includes("/quantic-vision-v7.css"),route+" must load authoritative Vision V7 CSS");
  }
  assert.ok(html.indexOf("/quantic-vision-id-gate.js")<html.indexOf("</head>"),route+" gate must load in head");
}

const home=fs.readFileSync("public/vision/index.html","utf8");
assert.ok(home.includes("/providence-v15-shell.js"),"Vision home must use common shell");
assert.ok(!home.includes('<header class="q-global-nav">'),"Vision home must not duplicate global nav");
assert.ok(!home.includes('<nav class="q-vision-subnav"'),"Vision home must not duplicate Vision nav");

const shell=fs.readFileSync("public/providence-v15-shell.js","utf8");
for(const route of ["/vision/","/predictions/","/analyst/","/alerts/","/sports/","/cameras/","/track-record/","/sources/","/backtest/","/settings/"]){
  assert.ok(shell.includes(route),route+" must remain visible in Vision navigation");
}
assert.ok(shell.includes("quantic-vision-v7.css"),"shell must keep Vision V7 for legacy feature pages");
assert.ok(shell.includes("visionNative"),"shell must skip legacy V7 on native Vision home");

const gate=fs.readFileSync("public/quantic-vision-id-gate.js","utf8");
for(const marker of ["position:fixed","inset:0","z-index:2147483647","MutationObserver","Quantic Identity Vault","Quantic Vision verrouillé","window.QuanticID"]){
  assert.ok(gate.includes(marker),marker);
}
assert.ok(!gate.includes("sessionStorage"),"Vision gate must not have a client-side bypass");

const css=fs.readFileSync("public/quantic-vision-v7.css","utf8");
for(const marker of [
  "body.q-vision-shell",
  ".q-vision-subnav",
  ".p15-pagehero",
  ".p168-hero",
  ".pv-panel",
  ".pv-setting-card",
  ".pa-chat",
  ".v5-section"
]) assert.ok(css.includes(marker),marker);

console.log(JSON.stringify({ok:true,contract:"vision-v7-quantic-id"}));
