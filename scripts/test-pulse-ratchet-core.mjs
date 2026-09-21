import assert from 'node:assert/strict';
import {
  b64u,
  preKeyTranscript,
  verifyPreKeyRecord,
  deriveInitiatorSession,
  deriveRecipientSession,
  supportsPostQuantumKEM
} from '../public/pulse/ratchet-core.js';
import {
  initInitiatorRatchet,
  initResponderRatchet,
  encryptRatchet,
  decryptRatchet,
  acknowledgeRatchetHandshake,
  ratchetDiagnostics
} from '../public/pulse/double-ratchet.js';

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
function meta(id,sender,recipient,at){
  return{clientMessageId:id,senderDeviceId:sender,recipientDeviceId:recipient,sentAt:at};
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
preKey.signature=b64u(await crypto.subtle.sign(
  {name:'Ed25519'},
  bob.signingPrivateKey,
  te.encode(preKeyTranscript(preKey))
));
assert.equal(await verifyPreKeyRecord(preKey,bob.signingPublicKey),true);

const handshake=await deriveInitiatorSession(alice,bob,preKey);
assert.equal(handshake.protocol,'pulse-session-v2');
assert.equal(handshake.handshake.profile,'classical-v2');

const sessionId='00000000-0000-4000-8000-000000000001';
const aliceState=await initInitiatorRatchet(handshake.rootKey,preKey.publicKey,{
  sessionId,
  pendingHandshake:handshake.handshake
});

const firstAt=new Date().toISOString();
const firstMeta=meta('m0',alice.deviceId,bob.deviceId,firstAt);
const first=await encryptRatchet(aliceState,'hello bob',firstMeta);
assert.ok(first.header.handshake,'initiator must attach the prekey handshake before peer acknowledgement');

const recipientHandshake=await deriveRecipientSession(
  bob,
  alice,
  {record:preKey,privateKey:prekeyPair.privateKey},
  first.header.handshake
);
assert.equal(recipientHandshake.profile,'classical-v2');

const bobState=await initResponderRatchet(
  recipientHandshake.rootKey,
  recipientHandshake.ratchetKeyPair,
  {sessionId}
);
assert.equal(await decryptRatchet(bobState,first,firstMeta),'hello bob');

const replyAt=new Date(Date.now()+1).toISOString();
const replyMeta=meta('r0',bob.deviceId,alice.deviceId,replyAt);
const reply=await encryptRatchet(bobState,'hello alice',replyMeta);
assert.equal(await decryptRatchet(aliceState,reply,replyMeta),'hello alice');
acknowledgeRatchetHandshake(aliceState);
assert.equal(ratchetDiagnostics(aliceState).awaitingPeer,false);

const sent=[];
for(let i=0;i<3;i++){
  const sentAt=new Date(Date.now()+10+i).toISOString();
  const m=meta('a'+(i+1),alice.deviceId,bob.deviceId,sentAt);
  sent.push({m,e:await encryptRatchet(aliceState,'ordered-'+i,m)});
}

// Deliver n=2 first. Bob must retain skipped keys for n=0 and n=1.
assert.equal(await decryptRatchet(bobState,sent[2].e,sent[2].m),'ordered-2');
assert.equal(ratchetDiagnostics(bobState).skipped,2);
assert.equal(await decryptRatchet(bobState,sent[0].e,sent[0].m),'ordered-0');
assert.equal(ratchetDiagnostics(bobState).skipped,1);
assert.equal(await decryptRatchet(bobState,sent[1].e,sent[1].m),'ordered-1');
assert.equal(ratchetDiagnostics(bobState).skipped,0);

await assert.rejects(
  ()=>decryptRatchet(bobState,sent[1].e,sent[1].m),
  /ratchet_message_replay/
);

const pqSupported=await supportsPostQuantumKEM();
assert.equal(typeof pqSupported,'boolean');

console.log(JSON.stringify({
  ok:true,
  contract:'pulse-session-v2-double-ratchet',
  prekeyVerified:true,
  initialAgreement:true,
  bidirectionalRatchet:true,
  outOfOrderDelivery:true,
  replayRejected:true,
  nativeMlKem768:pqSupported
}));
