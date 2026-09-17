import assert from 'node:assert/strict';
import { buildQuanticPortalStatus, QUANTIC_SERVICE_TARGETS } from '../src/quantic_portal_status.js';

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
  return { reachable: true, http_status: 200 };
}

const payload = await buildQuanticPortalStatus({ probe: concurrentProbe });
const activeResults = payload.services.filter(service => service.state !== 'pending');
assert.equal(started, active.length);
assert.equal(activeResults.length, active.length);
assert.ok(activeResults.every(service => service.reachable === true), 'active Quantic probes must start concurrently');
assert.equal(payload.services.find(service => service.id === 'relay-hostinger')?.state, 'pending');
console.log(JSON.stringify({ ok: true, concurrent_probes: active.length }));
