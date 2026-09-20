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
  ["/downloads/","Produits & outils"]
];
const navSources=[
  ["public/index.html","q-links"],
  ["public/downloads/index.html","q-links"],
  ["public/quantic/index.html","q-links"],
  ["public/mail/index.html","qn-global-links"],
  ["public/pulse/index.html","q-sillage-global-links"],
  ["public/news/index.html","q-links"],
  ["public/providence-v15-shell.js","q-global-links"],
  ["public/quantic-mail-portal-nav.js","qn-global-links"]
];

function navFragment(path,className){
  const s=read(path);
  const marker='class="'+className+'"';
  const start=s.indexOf(marker);
  assert.ok(start>=0,path+" missing "+className);
  const window=s.slice(start,start+2400);
  return window;
}

for(const [path,className] of navSources){
  const nav=navFragment(path,className);
  let last=-1;
  for(const [href,label] of canonical){
    const idx=nav.indexOf(href);
    assert.ok(idx>=0,path+" missing "+label);
    assert.ok(idx>last,path+" menu order changed at "+label);
    last=idx;
  }
  assert.ok(nav.includes("Quantic ID"),path+" missing Quantic ID");
}

assert.ok(fs.existsSync("public/news/index.html"),"native Quantic News route missing");
for(const path of ["public/index.html","public/downloads/index.html","public/quantic/index.html"]){
  assert.ok(read(path).includes("Quantic News"),path+" must surface Quantic News as a product");
}

const news=read("public/news/index.html");
assert.ok(news.includes("Quantic News"),"News page must identify product");
assert.ok(news.includes("/news/news.js"),"News runtime missing");
assert.ok(news.includes("/quantic-system-v6.css"),"News must share Quantic visual system");

const newsJs=read("public/news/news.js");
assert.ok(newsJs.includes("raw.githubusercontent.com/XDSawyerLoL/LEFILLIBRE"),"News feed fallback missing");

console.log(JSON.stringify({ok:true,contract:"global-nav-news-sports-overflow"}));
