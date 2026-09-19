import fs from "node:fs";
import assert from "node:assert/strict";

const read=p=>fs.readFileSync(p,"utf8");
const css=read("public/quantic-vision-v9.css");
for(const marker of [
  ".pv12-team-badge img",
  "object-fit:contain",
  ".fixture-card{",
  "overflow:hidden!important",
  'body[data-vision-ui="v9"] main',
  "overflow:visible!important"
]) assert.ok(css.includes(marker),marker);

const canonical=[
  ["/vision/","Vision"],
  ["/mail/","Mail"],
  ["/pulse/","Pulse"],
  ["/news/","News"],
  ["/network/","Network"],
  ["/products/","Produits"],
  ["/downloads/","Téléchargements"]
];
const files=[
  "public/index.html",
  "public/network/index.html",
  "public/products/index.html",
  "public/downloads/index.html",
  "public/quantic/index.html",
  "public/pulse/index.html",
  "public/providence-v15-shell.js",
  "public/quantic-mail-portal-nav.js"
];
for(const path of files){
  const s=read(path);
  let last=-1;
  for(const [href,label] of canonical){
    const token=href;
    const idx=s.indexOf(token);
    assert.ok(idx>=0,path+" missing "+label);
    assert.ok(idx>last,path+" menu order changed at "+label);
    last=idx;
  }
  assert.ok(s.includes("Quantic ID"),path+" missing Quantic ID");
}

assert.ok(fs.existsSync("public/news/index.html"),"native Quantic News route missing");
const news=read("public/news/index.html");
assert.ok(news.includes("Quantic News"),"News page must identify product");
assert.ok(news.includes("/news/news.js"),"News runtime missing");
assert.ok(news.includes("/quantic-system-v6.css"),"News must share Quantic visual system");

const newsJs=read("public/news/news.js");
assert.ok(newsJs.includes("raw.githubusercontent.com/XDSawyerLoL/LEFILLIBRE"),"News feed fallback missing");

console.log(JSON.stringify({ok:true,contract:"global-nav-news-sports-overflow"}));
