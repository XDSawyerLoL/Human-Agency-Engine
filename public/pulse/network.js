const DB_NAME='quantic-pulse-network';
const DB_VERSION=1;
const STORE='transport';
const KEY='primary';
const RELAY_STORAGE_KEY='quantic.relay-endpoints.v1';
const DEFAULT_RELAYS=[
  'https://quantic-network-relay-backup-production.up.railway.app',
  'https://quanticmail-network-relay.onrender.com',
  location.origin
];
const te=new TextEncoder();
const td=new TextDecoder();

function b64(bytes){
  const data=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes);
  let binary='';
  for(const byte of data)binary+=String.fromCharCode(byte);
  return btoa(binary);
}
function from64(value){
  const binary=atob(String(value||'')),out=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++)out[i]=binary.charCodeAt(i);
  return out;
}
function normalizeRelay(value){
  const raw=String(value||'').trim().replace(/\/$/,'');
  if(!raw)return'';
  try{
    const url=new URL(raw);
    const local=['localhost','127.0.0.1','::1','[::1]'].includes(url.hostname);
    if(url.protocol!=='https:'&&!(url.protocol==='http:'&&local))return'';
    if(url.username||url.password||url.search||url.hash)return'';
    return url.origin+(url.pathname==='/'?'':url.pathname.replace(/\/$/,''));
  }catch{return''}
}
function relayCandidates(){
  const values=[...DEFAULT_RELAYS];
  try{
    const custom=JSON.parse(localStorage.getItem(RELAY_STORAGE_KEY)||'[]');
    if(Array.isArray(custom))for(const relay of custom)if(relay?.enabled!==false&&relay?.baseUrl)values.unshift(relay.baseUrl);
  }catch{}
  return [...new Set(values.map(normalizeRelay).filter(Boolean))];
}
function openDb(){
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB_NAME,DB_VERSION);
    request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains(STORE))request.result.createObjectStore(STORE)};
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('secure_store_unavailable'));
  });
}
async function readTransport(){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,'readonly'),request=tx.objectStore(STORE).get(KEY);
    request.onsuccess=()=>resolve(request.result||null);
    request.onerror=()=>reject(request.error);
    tx.oncomplete=()=>db.close();
  });
}
async function saveTransport(value){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,'readwrite');
    tx.objectStore(STORE).put(value,KEY);
    tx.oncomplete=()=>{db.close();resolve(value)};
    tx.onerror=()=>{db.close();reject(tx.error)};
  });
}
async function nonExtractable(pair,algorithm,usages){
  const raw=await crypto.subtle.exportKey('pkcs8',pair.privateKey);
  return crypto.subtle.importKey('pkcs8',raw,algorithm,false,usages);
}
async function createTransport(pulseDeviceId){
  const enc=await crypto.subtle.generateKey({name:'ECDH',namedCurve:'P-256'},true,['deriveKey']);
  const sig=await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},true,['sign','verify']);
  const random=crypto.getRandomValues(new Uint8Array(32));
  const value={
    handle:'pulse_'+String(pulseDeviceId).replace(/[^a-f0-9]/gi,'').slice(-20).toLowerCase(),
    encryptionPrivateKey:await nonExtractable(enc,{name:'ECDH',namedCurve:'P-256'},['deriveKey']),
    signingPrivateKey:await nonExtractable(sig,{name:'ECDSA',namedCurve:'P-256'},['sign']),
    publicKey:await crypto.subtle.exportKey('jwk',enc.publicKey),
    signingPublicKey:await crypto.subtle.exportKey('jwk',sig.publicKey),
    authToken:b64(random),registrations:{}
  };
  random.fill(0);
  return saveTransport(value);
}
async function relayJson(base,path,init={},timeout=5000){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{
    const response=await fetch(base+path,{cache:'no-store',...init,signal:controller.signal});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||('relay_http_'+response.status));
    return data;
  }finally{clearTimeout(timer)}
}
async function registerRelay(transport,base){
  const challenge=await relayJson(base,'/api/quantic/challenge',{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({handle:transport.handle,publicKey:transport.publicKey,signingPublicKey:transport.signingPublicKey})
  });
  const signature=b64(await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},transport.signingPrivateKey,te.encode(challenge.challenge)));
  const result=await relayJson(base,'/api/quantic/register',{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({handle:transport.handle,publicKey:transport.publicKey,signingPublicKey:transport.signingPublicKey,authToken:transport.authToken,challenge:challenge.challenge,signature})
  });
  return{baseUrl:base,canonicalAddress:result.canonicalAddress,deviceId:result.rootDeviceId};
}
export async function ensurePulseNetworkDevice(pulseDeviceId,{refresh=false}={}){
  let transport=await readTransport();
  if(!transport?.encryptionPrivateKey||!transport?.signingPrivateKey)transport=await createTransport(pulseDeviceId);
  transport.registrations=transport.registrations||{};
  const known=Object.values(transport.registrations).filter(item=>item?.canonicalAddress&&item?.deviceId);
  const checkedAt=Date.parse(String(transport.lastCheckedAt||''));
  if(!refresh&&known.length&&Number.isFinite(checkedAt)&&Date.now()-checkedAt<5*60*1000){
    transport.canonicalAddress=known[0].canonicalAddress;
    transport.deviceId=known[0].deviceId;
    transport.relays=known.map(item=>item.baseUrl);
    return transport;
  }
  const relays=relayCandidates();
  await Promise.allSettled(relays.map(async base=>{transport.registrations[base]=await registerRelay(transport,base)}));
  const registrations=Object.values(transport.registrations).filter(item=>item?.canonicalAddress&&item?.deviceId);
  if(!registrations.length)throw new Error('secure_network_unavailable');
  const first=registrations[0];
  if(registrations.some(item=>item.canonicalAddress!==first.canonicalAddress||item.deviceId!==first.deviceId))throw new Error('secure_relay_identity_mismatch');
  transport.canonicalAddress=first.canonicalAddress;
  transport.deviceId=first.deviceId;
  transport.relays=registrations.map(item=>item.baseUrl);
  transport.lastCheckedAt=new Date().toISOString();
  await saveTransport(transport);
  return transport;
}
export function publicPulseNetworkRoute(transport){
  return{canonicalAddress:transport.canonicalAddress,deviceId:transport.deviceId,publicKey:transport.publicKey,relays:[...(transport.relays||[])]};
}
async function encryptOuter(publicKey,payload){
  const target=await crypto.subtle.importKey('jwk',publicKey,{name:'ECDH',namedCurve:'P-256'},false,[]);
  const ephemeral=await crypto.subtle.generateKey({name:'ECDH',namedCurve:'P-256'},true,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'ECDH',public:target},ephemeral.privateKey,{name:'AES-GCM',length:256},false,['encrypt']);
  const iv=crypto.getRandomValues(new Uint8Array(12));
  return{
    ciphertext:b64(await crypto.subtle.encrypt({name:'AES-GCM',iv},key,te.encode(JSON.stringify(payload)))),
    iv:b64(iv),
    ephemeralPublicKey:await crypto.subtle.exportKey('jwk',ephemeral.publicKey)
  };
}
async function decryptOuter(privateKey,envelope){
  const ephemeral=await crypto.subtle.importKey('jwk',envelope.ephemeralPublicKey,{name:'ECDH',namedCurve:'P-256'},false,[]);
  const key=await crypto.subtle.deriveKey({name:'ECDH',public:ephemeral},privateKey,{name:'AES-GCM',length:256},false,['decrypt']);
  const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:from64(envelope.iv)},key,from64(envelope.ciphertext));
  return JSON.parse(td.decode(clear));
}
export async function sendOverQuanticNetwork(pulseDeviceId,targetRoute,clientMessageId,payload){
  const transport=await ensurePulseNetworkDevice(pulseDeviceId);
  for(const base of targetRoute?.relays||[]){
    try{
      if(!transport.registrations[base])transport.registrations[base]=await registerRelay(transport,base);
      const own=transport.registrations[base],outer=await encryptOuter(targetRoute.publicKey,payload);
      await relayJson(base,'/api/quantic/send',{
        method:'POST',
        headers:{'content-type':'application/json',authorization:'Bearer '+transport.authToken},
        body:JSON.stringify({
          clientMessageId:String(clientMessageId).slice(0,100),
          from:own.canonicalAddress,fromDeviceId:own.deviceId,
          to:targetRoute.canonicalAddress,toDeviceId:targetRoute.deviceId,
          ciphertext:outer.ciphertext,iv:outer.iv,ephemeralPublicKey:outer.ephemeralPublicKey
        })
      });
      await saveTransport(transport);
      return{ok:true,relay:base};
    }catch{}
  }
  return{ok:false};
}
export async function pullFromQuanticNetwork(pulseDeviceId){
  const transport=await ensurePulseNetworkDevice(pulseDeviceId),packets=[];
  for(const [base,registration] of Object.entries(transport.registrations||{})){
    try{
      const data=await relayJson(base,'/api/quantic/pull?handle='+encodeURIComponent(registration.canonicalAddress)+'&deviceId='+encodeURIComponent(registration.deviceId),{
        headers:{authorization:'Bearer '+transport.authToken}
      });
      for(const envelope of data.envelopes||[]){
        try{
          packets.push({
            ...await decryptOuter(transport.encryptionPrivateKey,envelope),
            _relayFrom:envelope.from,
            _relayBase:base,
            _relayEnvelopeId:envelope.id
          });
        }catch{}
      }
    }catch{}
  }
  return packets;
}
export async function ackQuanticNetworkPackets(pulseDeviceId,packets){
  const transport=await ensurePulseNetworkDevice(pulseDeviceId),groups=new Map();
  for(const packet of packets||[]){
    if(!packet?._relayBase||!packet?._relayEnvelopeId)continue;
    const ids=groups.get(packet._relayBase)||[];
    ids.push(packet._relayEnvelopeId);
    groups.set(packet._relayBase,ids);
  }
  for(const [base,ids] of groups){
    const registration=transport.registrations?.[base];
    if(!registration)continue;
    await relayJson(base,'/api/quantic/ack',{
      method:'POST',
      headers:{'content-type':'application/json',authorization:'Bearer '+transport.authToken},
      body:JSON.stringify({handle:registration.canonicalAddress,deviceId:registration.deviceId,ids:[...new Set(ids)]})
    }).catch(()=>{});
  }
}
