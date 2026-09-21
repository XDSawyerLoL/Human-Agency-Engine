const te=new TextEncoder();
const PQ_ALGORITHM='ML-KEM-768';
let pqSupportPromise=null;

export function b64u(bytes){
  const data=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes);
  let binary='';
  for(const byte of data)binary+=String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
export function fromB64u(value){
  let text=String(value||'').replace(/-/g,'+').replace(/_/g,'/');
  text+='='.repeat((4-text.length%4)%4);
  const binary=atob(text),out=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++)out[i]=binary.charCodeAt(i);
  return out;
}
function concat(...parts){
  const arrays=parts.map(part=>part instanceof Uint8Array?part:new Uint8Array(part));
  const out=new Uint8Array(arrays.reduce((sum,part)=>sum+part.length,0));
  let offset=0;
  for(const part of arrays){out.set(part,offset);offset+=part.length}
  return out;
}
export function preKeyTranscript(record){
  const protocol=record?.protocol==='pulse-prekey-v2'?'pulse-prekey-v2':'pulse-prekey-v1';
  const base={
    protocol,
    deviceId:String(record.deviceId||''),
    preKeyId:String(record.preKeyId||''),
    publicKey:String(record.publicKey||''),
    createdAt:String(record.createdAt||''),
    expiresAt:String(record.expiresAt||'')
  };
  if(protocol==='pulse-prekey-v2'){
    base.pqAlgorithm=String(record.pqAlgorithm||'');
    base.pqPublicKey=String(record.pqPublicKey||'');
  }
  return JSON.stringify(base);
}
export async function importX25519Public(raw){
  return crypto.subtle.importKey('raw',fromB64u(raw),{name:'X25519'},false,[]);
}
export async function importEd25519Public(raw){
  return crypto.subtle.importKey('raw',fromB64u(raw),{name:'Ed25519'},false,['verify']);
}
export async function verifyPreKeyRecord(record,signingPublicKey){
  try{
    if(!['pulse-prekey-v1','pulse-prekey-v2'].includes(record?.protocol))return false;
    if(!/^[a-f0-9]{32}$/.test(String(record.preKeyId||'')))return false;
    if(fromB64u(record.publicKey).length!==32)return false;
    const expires=Date.parse(record.expiresAt),created=Date.parse(record.createdAt);
    if(!Number.isFinite(created)||!Number.isFinite(expires)||expires<=Date.now()||expires<=created)return false;
    if(record.protocol==='pulse-prekey-v2'){
      if(record.pqAlgorithm!==PQ_ALGORITHM)return false;
      if(fromB64u(record.pqPublicKey).length!==1184)return false;
    }
    const key=await importEd25519Public(signingPublicKey);
    return crypto.subtle.verify({name:'Ed25519'},key,fromB64u(record.signature),te.encode(preKeyTranscript(record)));
  }catch{return false}
}
async function dh(privateKey,publicRaw){
  const publicKey=await importX25519Public(publicRaw);
  return new Uint8Array(await crypto.subtle.deriveBits({name:'X25519',public:publicKey},privateKey,256));
}
async function sessionKdf(parts,context){
  const input=concat(...parts),salt=new Uint8Array(await crypto.subtle.digest('SHA-256',te.encode(context)));
  const material=await crypto.subtle.importKey('raw',input,'HKDF',false,['deriveBits']);
  input.fill(0);
  const bits=new Uint8Array(await crypto.subtle.deriveBits({
    name:'HKDF',hash:'SHA-256',salt,info:te.encode('pulse-session-v2/handshake')
  },material,512));
  return{rootKey:bits.slice(0,32),chainKey:bits.slice(32,64)};
}
export async function supportsPostQuantumKEM(){
  if(pqSupportPromise)return pqSupportPromise;
  pqSupportPromise=(async()=>{
    try{
      if(typeof crypto?.subtle?.encapsulateBits!=='function'||typeof crypto?.subtle?.decapsulateBits!=='function')return false;
      const pair=await crypto.subtle.generateKey({name:PQ_ALGORITHM},false,['encapsulateBits','decapsulateBits']);
      const raw=await crypto.subtle.exportKey('raw-public',pair.publicKey);
      return raw.byteLength===1184;
    }catch{return false}
  })();
  return pqSupportPromise;
}
export async function generatePostQuantumPreKey(){
  if(!await supportsPostQuantumKEM())return null;
  const pair=await crypto.subtle.generateKey({name:PQ_ALGORITHM},false,['encapsulateBits','decapsulateBits']);
  return{
    algorithm:PQ_ALGORITHM,
    privateKey:pair.privateKey,
    publicKey:b64u(await crypto.subtle.exportKey('raw-public',pair.publicKey))
  };
}
async function encapsulatePostQuantum(publicRaw){
  if(!await supportsPostQuantumKEM())throw new Error('secure_pq_unsupported');
  const publicKey=await crypto.subtle.importKey('raw-public',fromB64u(publicRaw),{name:PQ_ALGORITHM},false,['encapsulateBits']);
  const result=await crypto.subtle.encapsulateBits({name:PQ_ALGORITHM},publicKey);
  return{
    sharedKey:new Uint8Array(result.sharedKey),
    ciphertext:b64u(result.ciphertext)
  };
}
async function decapsulatePostQuantum(privateKey,ciphertext){
  if(!await supportsPostQuantumKEM())throw new Error('secure_pq_unsupported');
  return new Uint8Array(await crypto.subtle.decapsulateBits({name:PQ_ALGORITHM},privateKey,fromB64u(ciphertext)));
}
export async function deriveInitiatorSession(senderDevice,recipientDevice,preKey){
  const ephemeral=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const ephemeralPublicKey=b64u(await crypto.subtle.exportKey('raw',ephemeral.publicKey));
  const parts=[
    await dh(ephemeral.privateKey,recipientDevice.encryptionPublicKey),
    await dh(ephemeral.privateKey,preKey.publicKey),
    await dh(senderDevice.encryptionPrivateKey,preKey.publicKey)
  ];
  let profile='classical-v2',pqCiphertext='',pqAlgorithm='';
  if(preKey.protocol==='pulse-prekey-v2'){
    if(preKey.pqAlgorithm!==PQ_ALGORITHM||!preKey.pqPublicKey)throw new Error('secure_pq_prekey_invalid');
    const pq=await encapsulatePostQuantum(preKey.pqPublicKey);
    parts.push(pq.sharedKey);
    pqCiphertext=pq.ciphertext;
    pqAlgorithm=PQ_ALGORITHM;
    profile='hybrid-pq-v1';
  }
  const context=['pulse-x3dh-v2',profile,senderDevice.deviceId,recipientDevice.deviceId,preKey.preKeyId].join('|');
  const keys=await sessionKdf(parts,context);
  parts.forEach(part=>part.fill?.(0));
  return{
    ...keys,
    protocol:'pulse-session-v2',
    handshake:{
      protocol:'pulse-handshake-v2',
      preKeyId:preKey.preKeyId,
      ephemeralPublicKey,
      profile,
      pqAlgorithm,
      pqCiphertext
    }
  };
}
export async function deriveRecipientSession(recipientDevice,senderDevice,storedPreKey,handshake){
  const preKeyPrivate=storedPreKey?.privateKey;
  const preKeyRecord=storedPreKey?.record;
  if(!preKeyPrivate||!preKeyRecord)throw new Error('secure_prekey_missing');
  const profile=String(handshake?.profile||'classical-v2');
  const parts=[
    await dh(recipientDevice.encryptionPrivateKey,handshake.ephemeralPublicKey),
    await dh(preKeyPrivate,handshake.ephemeralPublicKey),
    await dh(preKeyPrivate,senderDevice.encryptionPublicKey)
  ];
  if(profile==='hybrid-pq-v1'){
    if(preKeyRecord.protocol!=='pulse-prekey-v2'||preKeyRecord.pqAlgorithm!==PQ_ALGORITHM||!storedPreKey.pqPrivateKey)throw new Error('secure_pq_prekey_missing');
    if(handshake.pqAlgorithm!==PQ_ALGORITHM||!handshake.pqCiphertext)throw new Error('secure_pq_handshake_invalid');
    const pqShared=await decapsulatePostQuantum(storedPreKey.pqPrivateKey,handshake.pqCiphertext);
    parts.push(pqShared);
  }else if(profile!=='classical-v2'){
    throw new Error('secure_handshake_profile_invalid');
  }
  const context=['pulse-x3dh-v2',profile,senderDevice.deviceId,recipientDevice.deviceId,handshake.preKeyId].join('|');
  const keys=await sessionKdf(parts,context);
  parts.forEach(part=>part.fill?.(0));
  return{
    ...keys,
    protocol:'pulse-session-v2',
    ratchetKeyPair:{
      privateKey:preKeyPrivate,
      publicKey:preKeyRecord.publicKey
    },
    profile
  };
}

// Compatibility helper retained for existing tests and older callers.
async function hmac(keyBytes,label){
  const key=await crypto.subtle.importKey('raw',keyBytes,{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC',key,te.encode(label)));
}
export async function advanceChain(chainKey,counter){
  const messageKey=await hmac(chainKey,'pulse-message-key|'+counter);
  const nextChainKey=await hmac(chainKey,'pulse-chain-key|'+counter);
  return{messageKey,nextChainKey,counter:counter+1};
}
export const POST_QUANTUM_ALGORITHM=PQ_ALGORITHM;
