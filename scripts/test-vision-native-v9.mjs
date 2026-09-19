import fs from "node:fs";
import assert from "node:assert/strict";

const nativePages=["alerts","sports","track-record","sources","backtest","settings"];
const forbidden=[
  "providence-v14.css",
  "providence-v15.css",
  "providence-v15-pages.css",
  "providence-v16-8-dynamic.css",
  "quantic-vision-v7.css"
];

for(const route of nativePages){
  const path=`public/${route}/index.html`;
  const html=fs.readFileSync(path,"utf8");
  assert.ok(html.includes("/quantic-vision-v9.css"),route+" must load Vision V9");
  for(const legacy of forbidden){
    assert.ok(!html.includes(legacy),route+" must not load "+legacy);
  }
  assert.ok(html.includes("/providence-v15-shell.js"),route+" keeps shared navigation shell");
}

const shell=fs.readFileSync("public/providence-v15-shell.js","utf8");
assert.ok(shell.includes("nativeV9Pages"),"shell must know native V9 pages");
assert.ok(shell.includes("quantic-vision-v9.css"),"shell must load V9 for native pages");
assert.ok(shell.includes("!nativeV9Pages.has(page)"),"legacy styles must be skipped for V9 pages");

const css=fs.readFileSync("public/quantic-vision-v9.css","utf8");
for(const marker of [
  "body[data-vision-ui=\"v9\"]",
  ".p15-pagehero",
  ".pv-kpis",
  ".p17-alert-card",
  ".sports-control-deck",
  ".fixture-card",
  ".pv-track-kpis",
  ".v4-source-card",
  ".pv-setting-card",
  ".pv-backtest-table"
]) assert.ok(css.includes(marker),marker);

assert.ok(!css.includes("background:#020713"),"V9 must not use Providence dark canvas");
assert.ok(!css.includes("linear-gradient(150deg,#071624,#040d18)"),"V9 must not reuse old dark panels");

console.log(JSON.stringify({ok:true,contract:"vision-native-v9-pages",pages:nativePages.length}));
