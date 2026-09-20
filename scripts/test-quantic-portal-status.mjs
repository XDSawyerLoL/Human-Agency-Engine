import assert from 'node:assert/strict';
import { buildQuanticPortalStatus, probeQuanticService, QUANTIC_SERVICE_TARGETS } from '../src/quantic_portal_status.js';

const active = QUANTIC_SERVICE_TARGETS.filter(target => target.state !== 'pending');
let started = 0;
let release;
const gate = new Promise(resolve => { release = resolve; });

async function concurrentProbe() {
  started += 1;
  if (started === active.length) release();
  await Promise.race([
    gate,
    new Promise((_, reject) => setTimeout(() => reject(new Error('probe-start-timeout')), 150)),
  ]);
  return { reachable: true, functional: true, http_status: 200, checked_at:new Date().toISOString() };
}

const payload = await buildQuanticPortalStatus({ probe: concurrentProbe });
const activeResults = payload.services.filter(service => service.state !== 'pending');
assert.equal(started, active.length);
assert.equal(activeResults.length, active.length);
assert.ok(activeResults.every(service => service.reachable === true && service.functional === true), 'active Quantic probes must start concurrently and remain truthful');
assert.equal(payload.services.find(service => service.id === 'relay-hostinger')?.state, 'pending');
assert.equal(payload.status,'degraded','a pending production relay must degrade the ecosystem status');

const protectedTarget={id:'vision',probe_url:'https://example.invalid/vision/',probe_contract:'protected-page'};
const protectedOk=await probeQuanticService(protectedTarget,{fetchImpl:async()=>({
  status:302,
  headers:{get:name=>String(name).toLowerCase()==='location'?'/quantic/?next=%2Fvision%2F':null}
})});
assert.equal(protectedOk.reachable,true);
assert.equal(protectedOk.functional,true);

const relayTarget={id:'relay-test',probe_url:'https://relay.invalid/api/quantic/health',probe_contract:'relay-health'};
const relay404=await probeQuanticService(relayTarget,{fetchImpl:async()=>({
  status:404,
  headers:{get:()=>null},
  clone(){return this},
  async json(){return {error:'not_found'}}
})});
assert.equal(relay404.reachable,true,'network reachability and service health are distinct');
assert.equal(relay404.functional,false,'HTTP 404 must never count as a functional relay');

const relayOk=await probeQuanticService(relayTarget,{fetchImpl:async()=>({
  status:200,
  headers:{get:()=>null},
  clone(){return this},
  async json(){return {ok:true,protocol:'quantic-relay/1'}}
})});
assert.equal(relayOk.functional,true);

console.log(JSON.stringify({ ok: true, concurrent_probes: active.length, truthful_health:true }));
