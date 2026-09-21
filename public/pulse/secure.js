import { api, state } from './core.js?v=16';
import { ensurePulseNetworkDevice, publicPulseNetworkRoute, sendOverQuanticNetwork, pullFromQuanticNetwork, ackQuanticNetworkPackets } from './network.js?v=16';
import { ensureSignedPreKeys } from './ratchet.js?v=16';

const PROTOCOL='pulse-e2ee-v1';
const DB_NAME='quantic-pulse-secure';
const DB_VERSION=2;
const DEVICE_STORE='device';
const TRUST_STORE='trust';
const INBOX_STORE='inbox';
const DEVICE_KEY='primary';
const te=new TextEncoder();
const td=new TextDecoder();

function b64u(bytes){
  const data=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes);
  let binary='';
  for(let i=0;i<data.length;i++)binary+=String.fromCharCode(data[i]);
  return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function fromB64u(value){
  const normalized=String(value||'').replace(/-/g,'+').replace(/_/g,'/');
  const padded=normalized+'='.repeat((4-normalized.length%4)%4);
  const binary=atob(padded),out=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++)out[i]=binary.charCodeAt(i);
  return out;
}
function concat(...parts){
  const arrays=parts.map(part=>part instanceof Uint8Array?part:new Uint8Array(part));
  const total=arrays.reduce((n,part)=>n+part.length,0),out=new Uint8Array(total);
  let offset=0;
  for(const part of arrays){out.set(part,offset);offset+=part.length}
  return out;
}
async function sha256Text(value){return new Uint8Array(await crypto.subtle.digest('SHA-256',te.encode(String(value))))}

function openDb(){
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB_NAME,DB_VERSION);
    request.onupgradeneeded=()=>{
      const db=request.result;
      if(!db.objectStoreNames.contains(DEVICE_STORE))db.createObjectStore(DEVICE_STORE);
      if(!db.objectStoreNames.contains(TRUST_STORE))db.createObjectStore(TRUST_STORE);
      if(!db.objectStoreNames.contains(INBOX_STORE))db.createObjectStore(INBOX_STORE);
    };
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('secure_store_unavailable'));
  });
}
async function dbGet(store,key){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,'readonly'),request=tx.objectStore(store).get(key);
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('secure_store_unavailable'));
    tx.oncomplete=()=>db.close();
  });
}
async function dbPut(store,key,value){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,'readwrite');
    tx.objectStore(store).put(value,key);
    tx.oncomplete=()=>{db.close();resolve(value)};
    tx.onerror=()=>{db.close();reject(tx.error||new Error('secure_store_unavailable'))};
  });
}
async function dbGetAll(store){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(store,'readonly'),request=tx.objectStore(store).getAll();
    request.onsuccess=()=>resolve(request.result||[]);
    request.onerror=()=>reject(request.error||new Error('secure_store_unavailable'));
    tx.oncomplete=()=>db.close();
  });
}

async function nonExtractablePrivate(pair,algorithm,usages){
  const pkcs8=await crypto.subtle.exportKey('pkcs8',pair.privateKey);
  return crypto.subtle.importKey('pkcs8',pkcs8,algorithm,false,usages);
}
async function createDevice(){
  if(!crypto?.subtle)throw new Error('secure_crypto_unsupported');
  let encPair,signPair;
  try{
    encPair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
    signPair=await crypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
  }catch{throw new Error('secure_crypto_unsupported')}
  const encryptionPrivateKey=await nonExtractablePrivate(encPair,{name:'X25519'},['deriveBits']);
  const signingPrivateKey=await nonExtractablePrivate(signPair,{name:'Ed25519'},['sign']);
  const encryptionPublicKey=b64u(await crypto.subtle.exportKey('raw',encPair.publicKey));
  const signingPublicKey=b64u(await crypto.subtle.exportKey('raw',signPair.publicKey));
  const device={
    deviceId:'pd_'+crypto.randomUUID().replace(/-/g,''),
    encryptionPrivateKey,signingPrivateKey,encryptionPublicKey,signingPublicKey,
    createdAt:new Date().toISOString(),protocol:PROTOCOL
  };
  await dbPut(DEVICE_STORE,DEVICE_KEY,device);
  return device;
}
export async function getSecureDevice(){
  const existing=await dbGet(DEVICE_STORE,DEVICE_KEY).catch(()=>null);
  if(existing?.deviceId&&existing?.encryptionPrivateKey&&existing?.signingPrivateKey&&existing?.encryptionPublicKey&&existing?.signingPublicKey)return existing;
  return createDevice();
}
function registrationBundle(device,transport){
  return{
    deviceId:device.deviceId,
    encryptionPublicKey:device.encryptionPublicKey,
    signingPublicKey:device.signingPublicKey,
    transport:publicPulseNetworkRoute(transport)
  };
}
export async function ensureSecureDevice(){
  if(!state.user)return null;
  const device=await getSecureDevice();
  const transport=await ensurePulseNetworkDevice(device.deviceId);
  const bundle=registrationBundle(device,transport);
  let current;
  try{current=await api('/api/pulse/secure/devices')}
  catch(error){
    if(device.pulseRegistered===true)return device;
    throw error;
  }
  const found=(current.devices||[]).find(item=>
    item.deviceId===device.deviceId&&
    item.encryptionPublicKey===device.encryptionPublicKey&&
    item.signingPublicKey===device.signingPublicKey&&
    item.transport?.canonicalAddress===bundle.transport.canonicalAddress
  );
  if(found){
    if(device.pulseRegistered!==true){device.pulseRegistered=true;await dbPut(DEVICE_STORE,DEVICE_KEY,device)}
    void ensureSignedPreKeys(device).catch(()=>{});
    return device;
  }
  if(!window.QuanticID?.assert)throw new Error('identity_vault_required');
  const challenge=await api('/api/pulse/secure/challenge',{method:'POST',body:JSON.stringify(bundle)});
  const identityProof=await window.QuanticID.assert({challenge:challenge.challenge,audience:challenge.audience});
  await api('/api/pulse/secure/devices',{method:'POST',body:JSON.stringify({...bundle,identityProof})});
  device.pulseRegistered=true;
  await dbPut(DEVICE_STORE,DEVICE_KEY,device);
  void ensureSignedPreKeys(device).catch(()=>{});
  return device;
}
async function trustBundle(handle,bundle){
  const key=String(handle||'').toLowerCase();
  const previous=await dbGet(TRUST_STORE,key).catch(()=>null);
  if(previous?.identityKeyId&&previous.identityKeyId!==bundle.identityKeyId){
    const error=new Error('secure_identity_changed');
    error.previous=previous.identityKeyId;
    error.current=bundle.identityKeyId;
    throw error;
  }
  await dbPut(TRUST_STORE,key,{
    identityKeyId:bundle.identityKeyId,
    firstSeenAt:previous?.firstSeenAt||new Date().toISOString(),
    updatedAt:new Date().toISOString(),
    bundle
  });
  return bundle;
}
export async function getSecureBundle(handle){
  const clean=String(handle||'').replace(/^@/,'').toLowerCase();
  try{
    const bundle=await api('/api/pulse/secure/bundle/'+encodeURIComponent(clean));
    if(bundle.protocol!==PROTOCOL)throw new Error('secure_protocol_mismatch');
    if(!(bundle.devices||[]).length)throw new Error('secure_recipient_unavailable');
    return trustBundle(clean,bundle);
  }catch(error){
    const cached=await dbGet(TRUST_STORE,clean).catch(()=>null);
    if(cached?.bundle?.protocol===PROTOCOL&&(cached.bundle.devices||[]).length)return cached.bundle;
    throw error;
  }
}
async function ownDevices(){
  try{
    const data=await api('/api/pulse/secure/devices');
    const devices=(data.devices||[]).filter(device=>device.protocol===PROTOCOL);
    if(devices.length)return devices;
  }catch{}
  const device=await getSecureDevice(),transport=await ensurePulseNetworkDevice(device.deviceId);
  return[{
    deviceId:device.deviceId,
    encryptionPublicKey:device.encryptionPublicKey,
    signingPublicKey:device.signingPublicKey,
    identityKeyId:'',
    registeredAt:device.createdAt,
    protocol:PROTOCOL,
    transport:publicPulseNetworkRoute(transport)
  }];
}
async function importX25519Public(raw){return crypto.subtle.importKey('raw',fromB64u(raw),{name:'X25519'},false,[])}
async function importEd25519Public(raw){return crypto.subtle.importKey('raw',fromB64u(raw),{name:'Ed25519'},false,['verify'])}
async function deriveAesKey(privateKey,publicKey,salt,info){
  const secret=new Uint8Array(await crypto.subtle.deriveBits({name:'X25519',public:publicKey},privateKey,256));
  const material=await crypto.subtle.importKey('raw',secret,'HKDF',false,['deriveKey']);
  secret.fill(0);
  return crypto.subtle.deriveKey({name:'HKDF',hash:'SHA-256',salt,info:te.encode(info)},material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
function envelopeUnsigned(envelope){
  return JSON.stringify({
    protocol:PROTOCOL,
    clientMessageId:envelope.clientMessageId,
    senderDeviceId:envelope.senderDeviceId,
    recipientDeviceId:envelope.recipientDeviceId,
    ephemeralPublicKey:envelope.ephemeralPublicKey,
    salt:envelope.salt,
    iv:envelope.iv,
    ciphertext:envelope.ciphertext,
    sentAt:envelope.sentAt
  });
}
async function encryptEnvelope(device,target,{clientMessageId,sentAt,plaintext}){
  const ephemeral=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const ephemeralPublicKey=b64u(await crypto.subtle.exportKey('raw',ephemeral.publicKey));
  const targetPublic=await importX25519Public(target.encryptionPublicKey);
  const salt=crypto.getRandomValues(new Uint8Array(32));
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const info=[PROTOCOL,clientMessageId,device.deviceId,target.deviceId].join('|');
  const aes=await deriveAesKey(ephemeral.privateKey,targetPublic,salt,info);
  const aad=te.encode([PROTOCOL,clientMessageId,device.deviceId,target.deviceId,sentAt].join('|'));
  const ciphertext=b64u(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad,tagLength:128},aes,te.encode(plaintext)));
  const envelope={clientMessageId,senderDeviceId:device.deviceId,recipientDeviceId:target.deviceId,ephemeralPublicKey,salt:b64u(salt),iv:b64u(iv),ciphertext,sentAt};
  envelope.signature=b64u(await crypto.subtle.sign({name:'Ed25519'},device.signingPrivateKey,te.encode(envelopeUnsigned(envelope))));
  return envelope;
}
export async function encryptMessageForHandle(handle,plaintext){
  const text=String(plaintext||'');
  if(!text.trim())throw new Error('empty_message');
  if(te.encode(text).length>3000)throw new Error('message_too_large');
  const device=await ensureSecureDevice();
  const [peer,ours]=await Promise.all([getSecureBundle(handle),ownDevices()]);
  const targets=new Map();
  for(const target of [...peer.devices,...ours])targets.set(target.deviceId,target);
  if(!targets.size)throw new Error('secure_recipient_unavailable');
  const clientMessageId=crypto.randomUUID(),sentAt=new Date().toISOString(),envelopes=[];
  for(const target of targets.values())envelopes.push(await encryptEnvelope(device,target,{clientMessageId,sentAt,plaintext:text}));
  return{handle:String(handle||'').replace(/^@/,''),protocol:PROTOCOL,clientMessageId,senderDeviceId:device.deviceId,sentAt,envelopes,peer};
}
async function verifyEnvelope(message,envelope){
  const sender=message.senderDevice;
  if(!sender?.signingPublicKey||sender.deviceId!==message.senderDeviceId)throw new Error('secure_sender_unverified');
  const publicKey=await importEd25519Public(sender.signingPublicKey);
  const material={
    clientMessageId:message.clientMessageId,
    senderDeviceId:message.senderDeviceId,
    recipientDeviceId:envelope.recipientDeviceId,
    ephemeralPublicKey:envelope.ephemeralPublicKey,
    salt:envelope.salt,
    iv:envelope.iv,
    ciphertext:envelope.ciphertext,
    sentAt:message.createdAt
  };
  return crypto.subtle.verify({name:'Ed25519'},publicKey,fromB64u(envelope.signature),te.encode(envelopeUnsigned(material)));
}
async function decryptOne(device,message){
  if(message.protocol!==PROTOCOL)return{...message,plaintext:String(message.body||''),legacy:true};
  const envelope=(message.envelopes||[]).find(item=>item.recipientDeviceId===device.deviceId);
  if(!envelope)return{...message,plaintext:'',secureUnavailable:true};
  if(!await verifyEnvelope(message,envelope))return{...message,plaintext:'',secureInvalid:true};
  const ephemeralPublic=await importX25519Public(envelope.ephemeralPublicKey);
  const salt=fromB64u(envelope.salt),iv=fromB64u(envelope.iv);
  const info=[PROTOCOL,message.clientMessageId,message.senderDeviceId,device.deviceId].join('|');
  const aes=await deriveAesKey(device.encryptionPrivateKey,ephemeralPublic,salt,info);
  const aad=te.encode([PROTOCOL,message.clientMessageId,message.senderDeviceId,device.deviceId,message.createdAt].join('|'));
  try{
    const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv,additionalData:aad,tagLength:128},aes,fromB64u(envelope.ciphertext));
    return{...message,plaintext:td.decode(clear),secure:true};
  }catch{return{...message,plaintext:'',secureInvalid:true}}
}
export async function decryptConversationMessages(messages){
  const device=await ensureSecureDevice();
  const out=[];
  for(const message of messages||[])out.push(await decryptOne(device,message));
  return out;
}

function messageStoreKey(message){
  return [String(message.clientMessageId||''),String(message.senderDeviceId||'')].join(':');
}
async function saveLocalMessage(message){
  await dbPut(INBOX_STORE,messageStoreKey(message),message);
  return message;
}
async function currentPublicDevice(){
  const device=await getSecureDevice();
  try{
    const data=await api('/api/pulse/secure/devices');
    const current=(data.devices||[]).find(item=>item.deviceId===device.deviceId);
    if(current)return current;
  }catch{}
  const transport=await ensurePulseNetworkDevice(device.deviceId);
  return{
    deviceId:device.deviceId,
    encryptionPublicKey:device.encryptionPublicKey,
    signingPublicKey:device.signingPublicKey,
    identityKeyId:'',
    protocol:PROTOCOL,
    transport:publicPulseNetworkRoute(transport)
  };
}
function sameSecureDevice(first,second){
  return !!first&&!!second&&
    first.deviceId===second.deviceId&&
    first.encryptionPublicKey===second.encryptionPublicKey&&
    first.signingPublicKey===second.signingPublicKey&&
    first.transport?.canonicalAddress===second.transport?.canonicalAddress;
}
export async function sendSecureMessage(handle,plaintext){
  const payload=await encryptMessageForHandle(handle,plaintext);
  const peerHandle=String(handle||'').replace(/^@/,'').toLowerCase();
  const senderDevice=await currentPublicDevice();
  let relayDelivered=0;

  for(const peerDevice of payload.peer.devices||[]){
    if(!peerDevice.transport)continue;
    const envelope=payload.envelopes.find(item=>item.recipientDeviceId===peerDevice.deviceId);
    if(!envelope)continue;
    const packet={
      format:'pulse-secure-relay-v1',
      version:1,
      senderHandle:state.user?.handle||'',
      recipientHandle:peerHandle,
      message:{
        id:'relay_'+payload.clientMessageId,
        clientMessageId:payload.clientMessageId,
        protocol:PROTOCOL,
        senderId:state.user?.id||'',
        recipientId:'',
        senderDeviceId:payload.senderDeviceId,
        createdAt:payload.sentAt,
        readAt:null,
        envelopes:[envelope],
        senderDevice
      }
    };
    const relayId=('ps:'+payload.clientMessageId+':'+peerDevice.deviceId.slice(-8)).slice(0,100);
    const delivered=await sendOverQuanticNetwork(payload.senderDeviceId,peerDevice.transport,relayId,packet).catch(()=>({ok:false}));
    if(delivered?.ok)relayDelivered++;
  }

  let central=false,centralError=null;
  try{
    await api('/api/pulse/messages',{
      method:'POST',
      body:JSON.stringify({
        handle:peerHandle,
        protocol:payload.protocol,
        clientMessageId:payload.clientMessageId,
        senderDeviceId:payload.senderDeviceId,
        sentAt:payload.sentAt,
        envelopes:payload.envelopes
      })
    });
    central=true;
  }catch(error){centralError=error}

  await saveLocalMessage({
    id:'local_'+payload.clientMessageId,
    clientMessageId:payload.clientMessageId,
    protocol:PROTOCOL,
    senderId:state.user?.id||'local',
    senderHandle:state.user?.handle||'',
    recipientHandle:peerHandle,
    recipientId:'',
    senderDeviceId:payload.senderDeviceId,
    createdAt:payload.sentAt,
    readAt:null,
    envelopes:payload.envelopes,
    senderDevice
  });

  if(!central&&!relayDelivered)throw centralError||new Error('secure_network_unavailable');
  return{ok:true,central,relayDelivered,clientMessageId:payload.clientMessageId};
}
export async function syncDecentralizedInbox(){
  const localDevice=await getSecureDevice();
  const packets=await pullFromQuanticNetwork(localDevice.deviceId).catch(()=>[]);
  const verifiedPackets=[];
  let accepted=0;
  for(const packet of packets){
    try{
      if(packet?.format!=='pulse-secure-relay-v1'||packet.version!==1||packet.message?.protocol!==PROTOCOL)continue;
      const senderHandle=String(packet.senderHandle||'').toLowerCase();
      const bundle=await getSecureBundle(senderHandle);
      const trusted=(bundle.devices||[]).find(item=>item.deviceId===packet.message.senderDeviceId);
      if(!trusted||!sameSecureDevice(trusted,packet.message.senderDevice))continue;
      if(trusted.transport?.canonicalAddress!==packet._relayFrom)continue;
      const message={
        ...packet.message,
        senderId:'remote:'+senderHandle,
        senderHandle,
        recipientHandle:String(packet.recipientHandle||'').toLowerCase(),
        senderDevice:trusted
      };
      await saveLocalMessage(message);
      verifiedPackets.push(packet);
      accepted++;
    }catch{}
  }
  if(verifiedPackets.length)await ackQuanticNetworkPackets(localDevice.deviceId,verifiedPackets).catch(()=>{});
  return accepted;
}
export async function decentralizedMessagesFor(handle){
  await syncDecentralizedInbox().catch(()=>{});
  const peer=String(handle||'').replace(/^@/,'').toLowerCase();
  const ours=String(state.user?.handle||'').toLowerCase();
  return (await dbGetAll(INBOX_STORE)).filter(message=>
    (message.senderHandle===peer&&message.recipientHandle===ours)||
    (message.senderHandle===ours&&message.recipientHandle===peer)
  );
}
export async function decentralizedConversationSummaries(){
  await syncDecentralizedInbox().catch(()=>{});
  const ours=String(state.user?.handle||'').toLowerCase();
  const grouped=new Map();
  for(const message of await dbGetAll(INBOX_STORE)){
    const sender=String(message.senderHandle||'').toLowerCase();
    const recipient=String(message.recipientHandle||'').toLowerCase();
    const peer=sender===ours?recipient:recipient===ours?sender:'';
    if(!peer)continue;
    const previous=grouped.get(peer);
    if(!previous||Date.parse(message.createdAt||0)>Date.parse(previous.createdAt||0)){
      grouped.set(peer,{handle:peer,createdAt:message.createdAt||new Date(0).toISOString(),encrypted:true});
    }
  }
  return [...grouped.values()].sort((a,b)=>Date.parse(b.createdAt)-Date.parse(a.createdAt));
}

export async function safetyNumber(handle){
  const [device,bundle,identity]=await Promise.all([ensureSecureDevice(),getSecureBundle(handle),window.QuanticID?.probe?.()]);
  const ids=[String(identity?.keyId||device.signingPublicKey),String(bundle.identityKeyId||'')].sort();
  const digest=await sha256Text(ids.join('|'));
  const digits=Array.from(digest.slice(0,15)).map(byte=>String(byte).padStart(3,'0')).join('');
  return digits.match(/.{1,5}/g).slice(0,9).join(' ');
}
export async function secureCapability(){
  try{
    const device=await ensureSecureDevice();
    return{ok:true,protocol:PROTOCOL,deviceId:device.deviceId};
  }catch(error){return{ok:false,error:error?.message||'secure_unavailable'}}
}
