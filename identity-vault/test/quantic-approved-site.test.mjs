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
 assert.match(source,/if\(!internalMail&&audience!==origin\)throw new Error\("quantic_audience_must_match_site"\)/);
 assert.doesNotMatch(source,/if\(isInternalMailOrigin\(origin\)&&audience==="quantic-mail-desktop"\)return/);
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

test('Windows OS lock and suspension revoke Vault access and pending hardware signs',()=>{
 assert.match(source,/powerMonitor\.on\("lock-screen",lockIdentity\)/);
 assert.match(source,/powerMonitor\.on\("suspend",lockIdentity\)/);
 assert.match(source,/powerMonitor\.getSystemIdleTime\(\)>=VAULT_IDLE_LOCK_SECONDS/);
 assert.match(source,/pendingHardwareSigns\.clear\(\);/);
 assert.match(source,/VAULT_IDLE_LOCK_SECONDS=15\*60/);
});
test('local Quantic Mail is not implicitly authorized to sign without consent',()=>{
 assert.match(source,/const internalMail=isInternalMailOrigin\(origin\)&&audience==="quantic-mail-desktop"/);
 assert.match(source,/dialog\.showMessageBoxSync/);
 assert.match(source,/approvedWebOrigins\.add\(key\)/);
});
