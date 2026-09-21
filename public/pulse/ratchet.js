import { api } from './core.js?v=17';
import {
  b64u,
  preKeyTranscript,
  verifyPreKeyRecord,
  deriveInitiatorSession,
  deriveRecipientSession,
  generatePostQuantumPreKey,
  supportsPostQuantumKEM,
  POST_QUANTUM_ALGORITHM
} from './ratchet-core.js?v=17';
import {
  RATCHET_PROTOCOL,
  initInitiatorRatchet,
  initResponderRatchet,
  encryptRatchet,
  decryptRatchet,
  acknowledgeRatchetHandshake,
  ratchetDiagnostics
} from './double-ratchet.js?v=17';

const DB='quantic-pulse-ratchet';
const VERSION=2;
const PREKEYS='prekeys';
const SESSIONS='sessions';
const te=new TextEncoder();
const locks=new Map();

function openDb(){
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB,VERSION);
    request.onupgradeneeded=()=>{
      const db=request.result;
      if(!db.objectStoreNames.contains(PREKEYS))db.createObjectStore(PREKEYS);
      if(!db.objectStoreNames.contains(SESSIONS))db.createObjectStore(SESSIONS);
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
async function withLock(key,operation){
  const previous=locks.get(key)||Promise.resolve();
  let release;
  const gate=new Promise(resolve=>{release=resolve});
  locks.set(key,previous.then(()=>gate));
  await previous;
  try{return await operation()}
  finally{
    release();
    if(locks.get(key)===gate)locks.delete(key);
  }
}
function preKeyId(){
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
}
async function nonExtractablePrivate(pair){
  const raw=await crypto.subtle.exportKey('pkcs8',pair.privateKey);
  return crypto.subtle.importKey('pkcs8',raw,{name:'X25519'},false,['deriveBits']);
}
async function createSignedPreKey(device,{hybrid=false}={}){
  const pair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const createdAt=new Date().toISOString();
  const expiresAt=new Date(Date.now()+14*24*60*60*1000).toISOString();
  const pq=hybrid?await generatePostQuantumPreKey():null;
  const record={
    protocol:pq?'pulse-prekey-v2':'pulse-prekey-v1',
    deviceId:device.deviceId,
    preKeyId:preKeyId(),
    publicKey:b64u(await crypto.subtle.exportKey('raw',pair.publicKey)),
    createdAt,
    expiresAt,
    ...(pq?{pqAlgorithm:pq.algorithm,pqPublicKey:pq.publicKey}:{})
  };
  record.signature=b64u(await crypto.subtle.sign({name:'Ed25519'},device.signingPrivateKey,te.encode(preKeyTranscript(record))));
  await put(PREKEYS,device.deviceId+':'+record.preKeyId,{
    record,
    privateKey:await nonExtractablePrivate(pair),
    ...(pq?{pqPrivateKey:pq.privateKey}:{})
  });
  return record;
}
function statusCount(status,deviceId,profile){
  const total=Number(status?.devices?.[deviceId]||0);
  const profiles=status?.profiles?.[deviceId]||{};
  if(profile==='hybrid')return Number(profiles.hybrid||0);
  if(profile==='classical')return Number(profiles.classical??total);
  return total;
}
export async function ensureSignedPreKeys(device,{minimum=8,target=16}={}){
  let status;
  try{status=await api('/api/pulse/secure/prekeys/status')}
  catch{return{ok:false,available:0}}
  const pqSupported=await supportsPostQuantumKEM();
  const classical=statusCount(status,device.deviceId,'classical');
  const hybrid=statusCount(status,device.deviceId,'hybrid');
  const records=[];
  if(classical<minimum){
    const count=Math.max(0,Math.min(24,target-classical));
    for(let i=0;i<count;i++)records.push(await createSignedPreKey(device,{hybrid:false}));
  }
  if(pqSupported&&hybrid<minimum){
    const count=Math.max(0,Math.min(24,target-hybrid));
    for(let i=0;i<count;i++)records.push(await createSignedPreKey(device,{hybrid:true}));
  }
  if(!records.length)return{ok:true,available:classical+hybrid,classical,hybrid,pqSupported};
  const result=await api('/api/pulse/secure/prekeys',{
    method:'POST',
    body:JSON.stringify({deviceId:device.deviceId,records})
  });
  return{
    ok:true,
    available:Number(result.available||classical+hybrid+records.length),
    classical:Number(result.profiles?.classical??classical),
    hybrid:Number(result.profiles?.hybrid??hybrid),
    accepted:Number(result.accepted||0),
    pqSupported
  };
}
export async function claimSignedPreKey(handle,recipientDevice,{profile='classical'}={}){
  const result=await api('/api/pulse/secure/prekeys/claim',{
    method:'POST',
    body:JSON.stringify({
      handle:String(handle||'').replace(/^@/,''),
      deviceId:recipientDevice.deviceId,
      profile
    })
  });
  if(!result.preKey||!await verifyPreKeyRecord(result.preKey,recipientDevice.signingPublicKey))throw new Error('secure_prekey_signature_invalid');
  if(profile==='hybrid'&&result.preKey.protocol!=='pulse-prekey-v2')throw new Error('secure_pq_downgrade_blocked');
  return result.preKey;
}
async function localPreKey(deviceId,preKeyId){
  return get(PREKEYS,deviceId+':'+preKeyId);
}
async function removeLocalPreKey(deviceId,preKeyId){
  return del(PREKEYS,deviceId+':'+preKeyId);
}
export async function consumeLocalPreKey(deviceId,preKeyId){
  const stored=await localPreKey(deviceId,preKeyId);
  if(!stored?.privateKey)throw new Error('secure_prekey_missing');
  await removeLocalPreKey(deviceId,preKeyId);
  return stored.privateKey;
}

function pairId(localDeviceId,remoteDeviceId){
  return String(localDeviceId)+'|'+String(remoteDeviceId);
}
function activeKey(localDeviceId,remoteDeviceId){
  return 'active|'+pairId(localDeviceId,remoteDeviceId);
}
function sessionKey(localDeviceId,remoteDeviceId,sessionId){
  return 'session|'+pairId(localDeviceId,remoteDeviceId)+'|'+String(sessionId);
}
async function activeSession(localDeviceId,remoteDeviceId){
  const sessionId=await get(SESSIONS,activeKey(localDeviceId,remoteDeviceId));
  if(!sessionId)return null;
  const state=await get(SESSIONS,sessionKey(localDeviceId,remoteDeviceId,sessionId));
  return state?{sessionId,state}:null;
}
async function storeSession(localDeviceId,remoteDeviceId,state,{activate=false}={}){
  await put(SESSIONS,sessionKey(localDeviceId,remoteDeviceId,state.sessionId),state);
  if(activate)await put(SESSIONS,activeKey(localDeviceId,remoteDeviceId),state.sessionId);
  return state;
}
async function choosePreKeyProfile(recipientDevice){
  const pq=await supportsPostQuantumKEM();
  if(!pq)return'classical';
  const pqCount=Number(recipientDevice?.pqPreKeyCount||0);
  return pqCount>0?'hybrid':'classical';
}
export async function encryptForRatchetDevice(localDevice,recipientDevice,handle,plaintext,meta){
  const lockId='send|'+pairId(localDevice.deviceId,recipientDevice.deviceId);
  return withLock(lockId,async()=>{
    let active=await activeSession(localDevice.deviceId,recipientDevice.deviceId);
    let state=active?.state;
    let profile=state?.profile||'';
    if(!state){
      const requested=await choosePreKeyProfile(recipientDevice);
      const preKey=await claimSignedPreKey(handle,recipientDevice,{profile:requested});
      const handshake=await deriveInitiatorSession(localDevice,recipientDevice,preKey);
      profile=handshake.handshake.profile;
      state=await initInitiatorRatchet(handshake.rootKey,preKey.publicKey,{
        pendingHandshake:handshake.handshake
      });
      state.profile=profile;
      handshake.rootKey.fill?.(0);
      await storeSession(localDevice.deviceId,recipientDevice.deviceId,state,{activate:true});
    }
    const encrypted=await encryptRatchet(state,plaintext,meta);
    await storeSession(localDevice.deviceId,recipientDevice.deviceId,state,{activate:true});
    return{
      recipientDeviceId:recipientDevice.deviceId,
      header:encrypted.header,
      iv:encrypted.iv,
      ciphertext:encrypted.ciphertext,
      profile,
      diagnostics:ratchetDiagnostics(state)
    };
  });
}
export async function decryptForRatchetDevice(localDevice,senderDevice,envelope,meta){
  const header=envelope?.header;
  if(!header?.sessionId)throw new Error('ratchet_header_invalid');
  const lockId='receive|'+pairId(localDevice.deviceId,senderDevice.deviceId);
  return withLock(lockId,async()=>{
    const key=sessionKey(localDevice.deviceId,senderDevice.deviceId,header.sessionId);
    let state=await get(SESSIONS,key);
    let consumedPreKeyId='';
    if(!state){
      const handshake=header.handshake;
      if(!handshake?.preKeyId||handshake.protocol!=='pulse-handshake-v2')throw new Error('ratchet_session_unknown');
      const stored=await localPreKey(localDevice.deviceId,handshake.preKeyId);
      if(!stored?.privateKey)throw new Error('secure_prekey_missing');
      const initial=await deriveRecipientSession(localDevice,senderDevice,stored,handshake);
      state=await initResponderRatchet(initial.rootKey,initial.ratchetKeyPair,{sessionId:header.sessionId});
      state.profile=initial.profile;
      initial.rootKey.fill?.(0);
      consumedPreKeyId=handshake.preKeyId;
    }
    const plaintext=await decryptRatchet(state,envelope,meta);
    acknowledgeRatchetHandshake(state);
    const current=await activeSession(localDevice.deviceId,senderDevice.deviceId);
    const activate=!current||current.sessionId===state.sessionId||!!consumedPreKeyId;
    await storeSession(localDevice.deviceId,senderDevice.deviceId,state,{activate});
    if(consumedPreKeyId)await removeLocalPreKey(localDevice.deviceId,consumedPreKeyId);
    return{plaintext,profile:state.profile||'classical-v2',diagnostics:ratchetDiagnostics(state)};
  });
}
export async function ratchetCapability(){
  const pq=await supportsPostQuantumKEM();
  return{
    protocol:RATCHET_PROTOCOL,
    doubleRatchet:true,
    outOfOrder:true,
    maxSkip:1000,
    pqHybrid:pq?POST_QUANTUM_ALGORITHM:null
  };
}

// Low-level helpers kept exported for focused tests.
export async function beginInitiatorSession(senderDevice,recipientDevice,handle){
  const profile=await choosePreKeyProfile(recipientDevice);
  const preKey=await claimSignedPreKey(handle,recipientDevice,{profile});
  return deriveInitiatorSession(senderDevice,recipientDevice,preKey);
}
export async function beginRecipientSession(recipientDevice,senderDevice,header){
  const stored=await localPreKey(recipientDevice.deviceId,header.preKeyId);
  if(!stored)throw new Error('secure_prekey_missing');
  return deriveRecipientSession(recipientDevice,senderDevice,stored,header);
}
