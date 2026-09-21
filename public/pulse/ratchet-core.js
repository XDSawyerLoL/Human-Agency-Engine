const te=new TextEncoder();

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
  return JSON.stringify({
    protocol:'pulse-prekey-v1',
    deviceId:String(record.deviceId||''),
    preKeyId:String(record.preKeyId||''),
    publicKey:String(record.publicKey||''),
    createdAt:String(record.createdAt||''),
    expiresAt:String(record.expiresAt||'')
  });
}
export async function importX25519Public(raw){
  return crypto.subtle.importKey('raw',fromB64u(raw),{name:'X25519'},false,[]);
}
export async function importEd25519Public(raw){
  return crypto.subtle.importKey('raw',fromB64u(raw),{name:'Ed25519'},false,['verify']);
}
export async function verifyPreKeyRecord(record,signingPublicKey){
  try{
    if(record?.protocol!=='pulse-prekey-v1')return false;
    if(!/^[a-f0-9]{32}$/.test(String(record.preKeyId||'')))return false;
    const expires=Date.parse(record.expiresAt),created=Date.parse(record.createdAt);
    if(!Number.isFinite(created)||!Number.isFinite(expires)||expires<=Date.now()||expires<=created)return false;
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
    name:'HKDF',hash:'SHA-256',salt,info:te.encode('pulse-session-v2')
  },material,512));
  return{rootKey:bits.slice(0,32),chainKey:bits.slice(32,64)};
}
export async function deriveInitiatorSession(senderDevice,recipientDevice,preKey){
  const ephemeral=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  const ephemeralPublicKey=b64u(await crypto.subtle.exportKey('raw',ephemeral.publicKey));
  const parts=[
    await dh(ephemeral.privateKey,recipientDevice.encryptionPublicKey),
    await dh(ephemeral.privateKey,preKey.publicKey),
    await dh(senderDevice.encryptionPrivateKey,preKey.publicKey)
  ];
  const context=['pulse-x3dh-v1',senderDevice.deviceId,recipientDevice.deviceId,preKey.preKeyId].join('|');
  const keys=await sessionKdf(parts,context);
  parts.forEach(part=>part.fill(0));
  return{...keys,ephemeralPublicKey,preKeyId:preKey.preKeyId,protocol:'pulse-session-v2'};
}
export async function deriveRecipientSession(recipientDevice,senderDevice,preKeyPrivate,header){
  const parts=[
    await dh(recipientDevice.encryptionPrivateKey,header.ephemeralPublicKey),
    await dh(preKeyPrivate,header.ephemeralPublicKey),
    await dh(preKeyPrivate,senderDevice.encryptionPublicKey)
  ];
  const context=['pulse-x3dh-v1',senderDevice.deviceId,recipientDevice.deviceId,header.preKeyId].join('|');
  const keys=await sessionKdf(parts,context);
  parts.forEach(part=>part.fill(0));
  return{...keys,protocol:'pulse-session-v2'};
}
async function hmac(keyBytes,label){
  const key=await crypto.subtle.importKey('raw',keyBytes,{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC',key,te.encode(label)));
}
export async function advanceChain(chainKey,counter){
  const messageKey=await hmac(chainKey,'pulse-message-key|'+counter);
  const nextChainKey=await hmac(chainKey,'pulse-chain-key|'+counter);
  return{messageKey,nextChainKey,counter:counter+1};
}
