import assert from 'node:assert/strict';
import {
  b64u,
  preKeyTranscript,
  verifyPreKeyRecord,
  deriveInitiatorSession,
  deriveRecipientSession,
  advanceChain
} from '../public/pulse/ratchet-core.js';

const te=new TextEncoder();

async function device(id){
  const encryption=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const signing=await crypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
  return{
    deviceId:id,
    encryptionPrivateKey:encryption.privateKey,
    encryptionPublicKey:b64u(await crypto.subtle.exportKey('raw',encryption.publicKey)),
    signingPrivateKey:signing.privateKey,
    signingPublicKey:b64u(await crypto.subtle.exportKey('raw',signing.publicKey))
  };
}

const alice=await device('alice-device');
const bob=await device('bob-device');
const prekeyPair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
const createdAt=new Date().toISOString();
const expiresAt=new Date(Date.now()+24*60*60*1000).toISOString();
const preKey={
  protocol:'pulse-prekey-v1',
  deviceId:bob.deviceId,
  preKeyId:'0123456789abcdef0123456789abcdef',
  publicKey:b64u(await crypto.subtle.exportKey('raw',prekeyPair.publicKey)),
  createdAt,
  expiresAt
};
preKey.signature=b64u(await crypto.subtle.sign({name:'Ed25519'},bob.signingPrivateKey,te.encode(preKeyTranscript(preKey))));

assert.equal(await verifyPreKeyRecord(preKey,bob.signingPublicKey),true);

const initiated=await deriveInitiatorSession(alice,bob,preKey);
const received=await deriveRecipientSession(
  bob,
  alice,
  prekeyPair.privateKey,
  {ephemeralPublicKey:initiated.ephemeralPublicKey,preKeyId:initiated.preKeyId}
);
assert.deepEqual([...initiated.rootKey],[...received.rootKey]);
assert.deepEqual([...initiated.chainKey],[...received.chainKey]);

const a1=await advanceChain(initiated.chainKey,0);
const b1=await advanceChain(received.chainKey,0);
assert.deepEqual([...a1.messageKey],[...b1.messageKey]);
assert.deepEqual([...a1.nextChainKey],[...b1.nextChainKey]);
assert.notDeepEqual([...a1.messageKey],[...a1.nextChainKey]);

const a2=await advanceChain(a1.nextChainKey,1);
assert.notDeepEqual([...a1.messageKey],[...a2.messageKey]);

console.log(JSON.stringify({
  ok:true,
  contract:'pulse-prekey-session-ratchet-core',
  prekeyVerified:true,
  initialAgreement:true,
  perMessageKeyRotation:true
}));
