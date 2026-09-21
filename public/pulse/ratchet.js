import { api } from './core.js?v=16';
import { b64u, preKeyTranscript, verifyPreKeyRecord, deriveInitiatorSession, deriveRecipientSession, advanceChain } from './ratchet-core.js?v=16';

const DB='quantic-pulse-ratchet';
const VERSION=1;
const PREKEYS='prekeys';
const SESSIONS='sessions';
const te=new TextEncoder();

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
function preKeyId(){
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
}
async function nonExtractablePrivate(pair){
  const raw=await crypto.subtle.exportKey('pkcs8',pair.privateKey);
  return crypto.subtle.importKey('pkcs8',raw,{name:'X25519'},false,['deriveBits']);
}
async function createSignedPreKey(device){
  const pair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const createdAt=new Date().toISOString();
  const expiresAt=new Date(Date.now()+14*24*60*60*1000).toISOString();
  const record={
    protocol:'pulse-prekey-v1',
    deviceId:device.deviceId,
    preKeyId:preKeyId(),
    publicKey:b64u(await crypto.subtle.exportKey('raw',pair.publicKey)),
    createdAt,
    expiresAt
  };
  record.signature=b64u(await crypto.subtle.sign({name:'Ed25519'},device.signingPrivateKey,te.encode(preKeyTranscript(record))));
  await put(PREKEYS,device.deviceId+':'+record.preKeyId,{
    record,
    privateKey:await nonExtractablePrivate(pair)
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
  return stored.privateKey;
}
export async function beginInitiatorSession(senderDevice,recipientDevice,handle){
  const preKey=await claimSignedPreKey(handle,recipientDevice);
  return deriveInitiatorSession(senderDevice,recipientDevice,preKey);
}
export async function beginRecipientSession(recipientDevice,senderDevice,header){
  const preKeyPrivate=await consumeLocalPreKey(recipientDevice.deviceId,header.preKeyId);
  return deriveRecipientSession(recipientDevice,senderDevice,preKeyPrivate,header);
}
export async function saveRatchetSession(id,session){
  return put(SESSIONS,id,session);
}
export async function loadRatchetSession(id){
  return get(SESSIONS,id);
}
export { advanceChain };
