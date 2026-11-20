import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../src/main.mjs',import.meta.url),'utf8');

test('SWAPP is an explicitly allowed origin, no broad https wildcard',()=>{
 assert.match(source,/"https:\/\/swapp\.tv"/);
 assert.match(source,/"https:\/\/www\.swapp\.tv"/);
 assert.doesNotMatch(source,/Access-Control-Allow-Origin"\s*:\s*"\*"/);
});
test('Quantic ID only signs on website approval and site-matching audience',()=>{
 assert.match(source,/approveQuanticSiteOrigin\(origin,input\.audience\)/);
 assert.match(source,/if\(audience!==origin\)throw new Error\("quantic_audience_must_match_site"\)/);
 assert.match(source,/dialog\.showMessageBoxSync/);
 assert.match(source,/quantic_site_authorization_denied/);
});
test('SWAPP cannot read QID or identity public key without site approval',()=>{
 assert.match(source,/keyId:mayRevealPublicIdentity\(origin\)\?status\.keyId:null/);
 assert.match(source,/publicKey:mayRevealPublicIdentity\(origin\)\?status\.publicKey:null/);
});
test('locking, removed USB and disconnected hardware clear website approvals',()=>{
 assert.match(source,/function lockIdentity\(\)\{\s*activeIdentity=null;\s*approvedWebOrigins\.clear\(\);/);
 assert.match(source,/hardware-disconnected[\s\S]*approvedWebOrigins\.clear\(\);/);
 assert.match(source,/startPresenceMonitor[\s\S]*approvedWebOrigins\.clear\(\);/);
});
