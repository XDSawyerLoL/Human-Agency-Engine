import { api } from './core.js?v=20';
import {
  b64u,fromB64u,preKeyTranscript,verifyPreKeyRecord,
  deriveInitiatorSession,deriveRecipientSession,
  generatePostQuantumPreKey
} from './ratchet-core.js?v=20';
import {
  initInitiatorRatchet,initResponderRatchet,
  encryptRatchet,decryptRatchet,acknowledgeRatchetHandshake,
  RATCHET_PROTOCOL
} from './double-ratchet.js?v=20';

const DB='quantic-pulse-ratchet';
const VERSION=3;
const PREKEYS='prekeys';
const SESSIONS='sessions';
const ACTIVE='active';
const PROFILES='profiles';
const te=new TextEncoder();

function openDb(){
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB,VERSION);
    request.onupgradeneeded=()=>{
      const db=request.result;
      for(const store of [PREKEYS,SESSIONS,ACTIVE,PROFILES])if(!db.objectStoreNames.contains(store))db.createObjectStore(store);
    };
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('ratchet_store_unavailable'));
  });
}
async function put(store,key,value){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,'readwrite');
    tx.objectStore(store).put(value,key);
    tx.oncomplete=()=>{db.close();resolve(value)};
    tx.onerror=()=>{db.close();reject(tx.error)};
  });
}
async function get(store,key){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,'readonly'),request=tx.objectStore(store).get(key);
    request.onsuccess=()=>resolve(request.result||null);
    request.onerror=()=>reject(request.error);
    tx.oncomplete=()=>db.close();
  });
}
async function del(store,key){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,'readwrite');
    tx.objectStore(store).delete(key);
    tx.oncomplete=()=>{db.close();resolve(true)};
    tx.onerror=()=>{db.close();reject(tx.error)};
  });
}
function preKeyId(){
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
}
async function nonExtractablePrivate(pair){
  const raw=await crypto.subtle.exportKey('pkcs8',pair.privateKey);
  return crypto.subtle.importKey('pkcs8',raw,{name:'X25519'},false,['deriveBits']);
}
async function createSignedPreKey(device){
  const pair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const pq=await generatePostQuantumPreKey().catch(()=>null);
  const createdAt=new Date().toISOString();
  const expiresAt=new Date(Date.now()+14*24*60*60*1000).toISOString();
  const record={
    protocol:pq?'pulse-prekey-v2':'pulse-prekey-v1',
    deviceId:device.deviceId,
    preKeyId:preKeyId(),
    publicKey:b64u(await crypto.subtle.exportKey('raw',pair.publicKey)),
    createdAt,
    expiresAt,
    ...(pq?{pqAlgorithm:pq.algorithm,pqPublicKey:pq.publicKey}:{})
  };
  record.signature=b64u(await crypto.subtle.sign(
    {name:'Ed25519'},
    device.signingPrivateKey,
    te.encode(preKeyTranscript(record))
  ));
  await put(PREKEYS,device.deviceId+':'+record.preKeyId,{
    record,
    privateKey:await nonExtractablePrivate(pair),
    ...(pq?{pqPrivateKey:pq.privateKey}:{})
  });
  return record;
}
export async function ensureSignedPreKeys(device,{minimum=12,target=24}={}){
  let status;
  try{status=await api('/api/pulse/secure/prekeys/status')}
  catch{return{ok:false,available:0}}
  const available=Number(status.devices?.[device.deviceId]||0);
  if(available>=minimum)return{ok:true,available};
  const count=Math.max(0,Math.min(32,target-available)),records=[];
  for(let i=0;i<count;i++)records.push(await createSignedPreKey(device));
  if(!records.length)return{ok:true,available};
  const result=await api('/api/pulse/secure/prekeys',{
    method:'POST',
    body:JSON.stringify({deviceId:device.deviceId,records})
  });
  return{ok:true,available:Number(result.available||available+records.length),accepted:Number(result.accepted||0)};
}
export async function claimSignedPreKey(handle,recipientDevice){
  const result=await api('/api/pulse/secure/prekeys/claim',{
    method:'POST',
    body:JSON.stringify({handle:String(handle||'').replace(/^@/,''),deviceId:recipientDevice.deviceId})
  });
  if(!result.preKey||!await verifyPreKeyRecord(result.preKey,recipientDevice.signingPublicKey))throw new Error('secure_prekey_signature_invalid');
  return result.preKey;
}
export async function consumeLocalPreKey(deviceId,preKeyId){
  const key=deviceId+':'+preKeyId,stored=await get(PREKEYS,key);
  if(!stored?.privateKey)throw new Error('secure_prekey_missing');
  await del(PREKEYS,key);
  return stored;
}
function profileRank(profile){return profile==='hybrid-pq-v1'?2:profile==='classical-v2'?1:0}
async function enforcePeerProfile(peerDeviceId,profile){
  const key='peer:'+String(peerDeviceId),previous=await get(PROFILES,key);
  if(previous&&profileRank(profile)<profileRank(previous.profile))throw new Error('secure_pq_downgrade');
  if(!previous||profileRank(profile)>profileRank(previous.profile)){
    await put(PROFILES,key,{profile,updatedAt:new Date().toISOString()});
  }
  return profile;
}
function activeKey(peerDeviceId){return 'peer:'+String(peerDeviceId)}
async function setActive(peerDeviceId,sessionId){await put(ACTIVE,activeKey(peerDeviceId),String(sessionId))}
async function getActive(peerDeviceId){return get(ACTIVE,activeKey(peerDeviceId))}
export async function saveRatchetSession(state,peerDeviceId){
  if(!state?.sessionId)throw new Error('ratchet_session_id_required');
  await put(SESSIONS,state.sessionId,state);
  if(peerDeviceId)await setActive(peerDeviceId,state.sessionId);
  return state;
}
export async function loadRatchetSession(sessionId){return get(SESSIONS,String(sessionId||''))}
export async function loadActiveRatchetSession(peerDeviceId){
  const id=await getActive(peerDeviceId);
  return id?loadRatchetSession(id):null;
}
function envelopeTranscript(meta,envelope){
  return JSON.stringify({
    protocol:RATCHET_PROTOCOL,
    clientMessageId:String(meta.clientMessageId||''),
    senderDeviceId:String(meta.senderDeviceId||''),
    recipientDeviceId:String(meta.recipientDeviceId||''),
    sentAt:String(meta.sentAt||''),
    header:envelope.header,
    iv:String(envelope.iv||''),
    ciphertext:String(envelope.ciphertext||'')
  });
}
async function signEnvelope(device,meta,envelope){
  return b64u(await crypto.subtle.sign(
    {name:'Ed25519'},
    device.signingPrivateKey,
    te.encode(envelopeTranscript(meta,envelope))
  ));
}
export async function verifyRatchetEnvelope(senderDevice,meta,envelope){
  try{
    if(envelope?.protocol!==RATCHET_PROTOCOL||!senderDevice?.signingPublicKey)return false;
    const key=await crypto.subtle.importKey('raw',fromB64u(senderDevice.signingPublicKey),{name:'Ed25519'},false,['verify']);
    return crypto.subtle.verify(
      {name:'Ed25519'},
      key,
      fromB64u(envelope.signature),
      te.encode(envelopeTranscript(meta,envelope))
    );
  }catch{return false}
}
export async function encryptSessionMessage(senderDevice,recipientDevice,handle,plaintext,meta){
  let state=await loadActiveRatchetSession(recipientDevice.deviceId);
  if(!state){
    const preKey=await claimSignedPreKey(handle,recipientDevice);
    const handshake=await deriveInitiatorSession(senderDevice,recipientDevice,preKey);
    await enforcePeerProfile(recipientDevice.deviceId,handshake.handshake.profile);
    state=await initInitiatorRatchet(handshake.rootKey,preKey.publicKey,{
      sessionId:crypto.randomUUID(),
      pendingHandshake:handshake.handshake
    });
    state.securityProfile=handshake.handshake.profile;
  }
  const recipientMeta={...meta,recipientDeviceId:recipientDevice.deviceId};
  const encrypted=await encryptRatchet(state,plaintext,recipientMeta);
  const envelope={
    protocol:RATCHET_PROTOCOL,
    recipientDeviceId:recipientDevice.deviceId,
    header:encrypted.header,
    iv:encrypted.iv,
    ciphertext:encrypted.ciphertext
  };
  envelope.signature=await signEnvelope(senderDevice,recipientMeta,envelope);
  await saveRatchetSession(state,recipientDevice.deviceId);
  return envelope;
}
export async function decryptSessionMessage(localDevice,senderDevice,message,envelope){
  const meta={
    clientMessageId:message.clientMessageId,
    senderDeviceId:message.senderDeviceId,
    recipientDeviceId:localDevice.deviceId,
    sentAt:message.createdAt
  };
  if(!await verifyRatchetEnvelope(senderDevice,meta,envelope))throw new Error('secure_sender_unverified');
  const sessionId=String(envelope.header?.sessionId||'');
  let state=await loadRatchetSession(sessionId);
  if(!state){
    const handshake=envelope.header?.handshake;
    if(!handshake)throw new Error('ratchet_session_missing');
    const stored=await consumeLocalPreKey(localDevice.deviceId,handshake.preKeyId);
    const initial=await deriveRecipientSession(localDevice,senderDevice,stored,handshake);
    await enforcePeerProfile(senderDevice.deviceId,initial.profile);
    state=await initResponderRatchet(initial.rootKey,initial.ratchetKeyPair,{sessionId});
    state.securityProfile=initial.profile;
  }
  const plaintext=await decryptRatchet(state,envelope,meta);
  acknowledgeRatchetHandshake(state);
  await saveRatchetSession(state,senderDevice.deviceId);
  return plaintext;
}
export async function ratchetCapability(){
  try{
    const probe=await generatePostQuantumPreKey().catch(()=>null);
    return{
      protocol:RATCHET_PROTOCOL,
      doubleRatchet:'dh-double-ratchet-v1',
      postQuantum:probe?'hybrid-ml-kem-768':'classical-x25519'
    };
  }catch{
    return{protocol:RATCHET_PROTOCOL,doubleRatchet:'dh-double-ratchet-v1',postQuantum:'classical-x25519'};
  }
}
