import assert from 'node:assert/strict';
import fs from 'node:fs';
const read=path=>fs.readFileSync(path,'utf8');
for(const module of ['app','session','views','secure','render','ratchet']){
  const source=read('public/pulse/'+module+'.js');
  assert.ok(source.includes("'./core.js?v=25'"),module+' imports a different core.js module instance');
  assert.ok(!source.includes("'./core.js?v=21'")&&!source.includes("'./core.js?v=22'"),module+' still loads a stale state');
}
const app=read('public/pulse/app.js');
const views=read('public/pulse/views.js');
const session=read('public/pulse/session.js');
const html=read('public/pulse/index.html');
assert.ok(app.includes("'./session.js?v=25'"));
assert.ok(views.includes("'./session.js?v=25'"));
assert.ok(html.includes('/pulse/app.js?v=25'));
assert.ok(html.includes('Bienvenue sur SOCIAL'));
assert.ok(!html.includes('Bienvenue sur ZOON'));
assert.ok(session.includes('retryIdentityConnection'));
assert.ok(session.includes('Cache display only.'));
assert.ok(session.includes("state.identityStatus='connected'"));
assert.ok(session.includes('failedBridgeProbes>=6'));
assert.ok(app.includes('setInterval(reconnect,60000)'));
const mailGate=read('public/quantic-mail-id-gate.js');
assert.ok(mailGate.includes('retryTimer=setInterval'));
assert.ok(mailGate.includes('checkInFlight'));
for(const backend of ['src/quantic_identity.js','src/quantic_pulse.js']){
 const source=read(backend);
 assert.ok(source.includes("from './quantic_base64url.js'"));
 assert.ok(!/Buffer\.from\([^\n]+['"]base64url['"]/.test(source));
}
console.log(JSON.stringify({ok:true,contract:'social-quantic-id-unified-state-and-encoding'}));
