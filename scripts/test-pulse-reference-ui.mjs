import fs from "node:fs";
import assert from "node:assert/strict";

const html=fs.readFileSync("public/pulse/index.html","utf8");
const css=fs.readFileSync("public/pulse/pulse.css","utf8");
const backend=fs.readFileSync("src/quantic_pulse.js","utf8");
const server=fs.readFileSync("server_core.js","utf8");

for(const marker of [
  'class="pulse-sidebar"',
  'class="pulse-main"',
  'class="pulse-right"',
  'id="pulse-welcome"',
  'id="auth-modal"',
  'class="pulse-mobile-nav"',
  'id="compose-focus"',
  'id="circle-preview"'
]) assert.ok(html.includes(marker),marker);

assert.ok(html.includes('href="/mail/"'));
assert.ok(html.includes('type="module" src="/pulse/app.js'));
assert.ok(css.includes('grid-template-columns:250px minmax(0,680px) 360px'));
assert.ok(css.includes('.pulse-sidebar'));
assert.ok(css.includes('.pulse-right'));
assert.ok(css.includes('.pulse-welcome'));

for(const route of [
  "/api/pulse/auth/register",
  "/api/pulse/auth/login",
  "/api/pulse/search",
  "/api/pulse/circles",
  "/api/pulse/notifications",
  "/api/pulse/conversations",
  "/api/pulse/export"
]) assert.ok(backend.includes(route),route);

assert.ok(server.indexOf("installQuanticPulse(app)")<server.indexOf("app.use(express.json"),"Pulse raw handler must run before express.json consumes the request body");

console.log(JSON.stringify({ok:true,contract:"pulse-reference-ui-full"}));
