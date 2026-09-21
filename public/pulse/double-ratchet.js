import { b64u, fromB64u, importX25519Public } from './ratchet-core.js?v=18';

const te=new TextEncoder();
const td=new TextDecoder();
export const RATCHET_PROTOCOL='pulse-session-v2';
export const MAX_SKIP=1000;
export const MAX_STORED_SKIPPED=2000;

function concat(...parts){
  const arrays=parts.map(part=>part instanceof Uint8Array?part:new Uint8Array(part));
  const out=new Uint8Array(arrays.reduce((sum,part)=>sum+part.length,0));
  let offset=0;
  for(const part of arrays){out.set(part,offset);offset+=part.length}
  return out;
}
async function importHmac(raw){
  return crypto.subtle.importKey('raw',raw,{name:'HMAC',hash:'SHA-256'},false,['sign']);
}
async function hmac(raw,data){
  const key=await importHmac(raw);
  return new Uint8Array(await crypto.subtle.sign('HMAC',key,data instanceof Uint8Array?data:te.encode(String(data))));
}
async function hkdf(ikm,salt,info,length=64){
  const key=await crypto.subtle.importKey('raw',ikm,'HKDF',false,['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({
    name:'HKDF',hash:'SHA-256',salt,info:te.encode(info)
  },key,length*8));
}
async function dh(privateKey,publicRaw){
  const publicKey=await importX25519Public(publicRaw);
  return new Uint8Array(await crypto.subtle.deriveBits({name:'X25519',public:publicKey},privateKey,256));
}
async function nonExtractableX25519(privateKey){
  if(privateKey.extractable===false)return privateKey;
  const pkcs8=await crypto.subtle.exportKey('pkcs8',privateKey);
  return crypto.subtle.importKey('pkcs8',pkcs8,{name:'X25519'},false,['deriveBits']);
}
export async function generateRatchetKeyPair(){
  const pair=await crypto.subtle.generateKey({name:'X25519'},true,['deriveBits']);
  return{
    privateKey:await nonExtractableX25519(pair.privateKey),
    publicKey:b64u(await crypto.subtle.exportKey('raw',pair.publicKey))
  };
}
export async function kdfRoot(rootKey,dhOutput){
  const out=await hkdf(dhOutput,rootKey,'pulse-double-ratchet-v1/root',64);
  return{rootKey:out.slice(0,32),chainKey:out.slice(32,64)};
}
export async function kdfChain(chainKey){
  if(!chainKey)throw new Error('ratchet_chain_missing');
  const key=chainKey instanceof Uint8Array?chainKey:new Uint8Array(chainKey);
  const messageKey=await hmac(key,new Uint8Array([1]));
  const nextChainKey=await hmac(key,new Uint8Array([2]));
  return{messageKey,nextChainKey};
}
function skippedId(dhPublic,n){return String(dhPublic)+'|'+Number(n)}
function skippedCount(state){return Object.keys(state.skipped||{}).length}
function assertCounter(value){
  return Number.isSafeInteger(value)&&value>=0&&value<=0x7fffffff;
}
function headerMaterial(header){
  return JSON.stringify({
    sessionId:String(header.sessionId||''),
    dh:String(header.dh||''),
    pn:Number(header.pn||0),
    n:Number(header.n||0),
    handshake:header.handshake?{
      protocol:String(header.handshake.protocol||''),
      preKeyId:String(header.handshake.preKeyId||''),
      ephemeralPublicKey:String(header.handshake.ephemeralPublicKey||''),
      profile:String(header.handshake.profile||''),
      pqAlgorithm:String(header.handshake.pqAlgorithm||''),
      pqCiphertext:String(header.handshake.pqCiphertext||'')
    }:null
  });
}
export function ratchetAssociatedData(meta,header){
  return te.encode(JSON.stringify({
    protocol:RATCHET_PROTOCOL,
    clientMessageId:String(meta.clientMessageId||''),
    senderDeviceId:String(meta.senderDeviceId||''),
    recipientDeviceId:String(meta.recipientDeviceId||''),
    sentAt:String(meta.sentAt||''),
    header:JSON.parse(headerMaterial(header))
  }));
}
async function aesKey(messageKey){
  return crypto.subtle.importKey('raw',messageKey,{name:'AES-GCM'},false,['encrypt','decrypt']);
}
async function skipMessageKeys(state,until){
  if(!assertCounter(until))throw new Error('ratchet_header_invalid');
  if(state.Nr+MAX_SKIP<until)throw new Error('ratchet_too_many_skipped');
  if(!state.CKr){
    if(until===0)return;
    throw new Error('ratchet_receive_chain_missing');
  }
  while(state.Nr<until){
    if(skippedCount(state)>=MAX_STORED_SKIPPED)throw new Error('ratchet_skipped_store_full');
    const step=await kdfChain(state.CKr);
    state.CKr=step.nextChainKey;
    state.skipped=state.skipped||{};
    state.skipped[skippedId(state.DHr,state.Nr)]=b64u(step.messageKey);
    state.Nr++;
  }
}
async function dhRatchet(state,remoteDh){
  state.PN=state.Ns;
  state.Ns=0;
  state.Nr=0;
  state.DHr=remoteDh;

  const receiveDh=await dh(state.DHs.privateKey,state.DHr);
  const receiveRoot=await kdfRoot(state.RK,receiveDh);
  receiveDh.fill(0);
  state.RK=receiveRoot.rootKey;
  state.CKr=receiveRoot.chainKey;

  state.DHs=await generateRatchetKeyPair();
  const sendDh=await dh(state.DHs.privateKey,state.DHr);
  const sendRoot=await kdfRoot(state.RK,sendDh);
  sendDh.fill(0);
  state.RK=sendRoot.rootKey;
  state.CKs=sendRoot.chainKey;
}
export async function initInitiatorRatchet(sharedSecret,remoteRatchetPublic,{sessionId=crypto.randomUUID(),pendingHandshake=null}={}){
  const state={
    protocol:RATCHET_PROTOCOL,
    sessionId,
    RK:new Uint8Array(sharedSecret),
    DHs:await generateRatchetKeyPair(),
    DHr:String(remoteRatchetPublic||''),
    CKs:null,
    CKr:null,
    Ns:0,Nr:0,PN:0,
    skipped:{},
    pendingHandshake,
    createdAt:new Date().toISOString(),
    updatedAt:new Date().toISOString()
  };
  const out=await dh(state.DHs.privateKey,state.DHr);
  const root=await kdfRoot(state.RK,out);
  out.fill(0);
  state.RK=root.rootKey;
  state.CKs=root.chainKey;
  return state;
}
export async function initResponderRatchet(sharedSecret,localRatchetPair,{sessionId}={}){
  if(!sessionId)throw new Error('ratchet_session_id_required');
  return{
    protocol:RATCHET_PROTOCOL,
    sessionId,
    RK:new Uint8Array(sharedSecret),
    DHs:{
      privateKey:localRatchetPair.privateKey,
      publicKey:localRatchetPair.publicKey
    },
    DHr:null,
    CKs:null,
    CKr:null,
    Ns:0,Nr:0,PN:0,
    skipped:{},
    pendingHandshake:null,
    createdAt:new Date().toISOString(),
    updatedAt:new Date().toISOString()
  };
}
export async function encryptRatchet(state,plaintext,meta){
  if(state.protocol!==RATCHET_PROTOCOL||!state.CKs)throw new Error('ratchet_send_chain_missing');
  const step=await kdfChain(state.CKs);
  state.CKs=step.nextChainKey;
  const header={
    sessionId:state.sessionId,
    dh:state.DHs.publicKey,
    pn:state.PN,
    n:state.Ns,
    ...(state.pendingHandshake?{handshake:state.pendingHandshake}:{})
  };
  state.Ns++;
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const aad=ratchetAssociatedData(meta,header);
  const ciphertext=await crypto.subtle.encrypt(
    {name:'AES-GCM',iv,additionalData:aad,tagLength:128},
    await aesKey(step.messageKey),
    te.encode(String(plaintext))
  );
  step.messageKey.fill(0);
  state.updatedAt=new Date().toISOString();
  return{header,iv:b64u(iv),ciphertext:b64u(ciphertext)};
}
async function decryptWithKey(messageKey,envelope,meta){
  try{
    const clear=await crypto.subtle.decrypt(
      {name:'AES-GCM',iv:fromB64u(envelope.iv),additionalData:ratchetAssociatedData(meta,envelope.header),tagLength:128},
      await aesKey(messageKey),
      fromB64u(envelope.ciphertext)
    );
    return td.decode(clear);
  }finally{
    if(messageKey?.fill)messageKey.fill(0);
  }
}
export async function decryptRatchet(state,envelope,meta){
  const header=envelope?.header;
  if(!header||header.sessionId!==state.sessionId||!assertCounter(header.n)||!assertCounter(header.pn))throw new Error('ratchet_header_invalid');

  state.skipped=state.skipped||{};
  const cachedId=skippedId(header.dh,header.n);
  if(state.skipped[cachedId]){
    const key=fromB64u(state.skipped[cachedId]);
    delete state.skipped[cachedId];
    const plaintext=await decryptWithKey(key,envelope,meta);
    state.updatedAt=new Date().toISOString();
    return plaintext;
  }

  if(state.DHr!==header.dh){
    await skipMessageKeys(state,header.pn);
    await dhRatchet(state,header.dh);
  }
  if(header.n<state.Nr)throw new Error('ratchet_message_replay');
  await skipMessageKeys(state,header.n);
  if(!state.CKr)throw new Error('ratchet_receive_chain_missing');
  const step=await kdfChain(state.CKr);
  state.CKr=step.nextChainKey;
  state.Nr++;
  const plaintext=await decryptWithKey(step.messageKey,envelope,meta);
  state.updatedAt=new Date().toISOString();
  return plaintext;
}
export function acknowledgeRatchetHandshake(state){
  if(state.pendingHandshake){
    state.pendingHandshake=null;
    state.updatedAt=new Date().toISOString();
  }
  return state;
}
export function ratchetDiagnostics(state){
  return{
    protocol:state?.protocol||'',
    sessionId:state?.sessionId||'',
    sendCount:Number(state?.Ns||0),
    receiveCount:Number(state?.Nr||0),
    previousSendCount:Number(state?.PN||0),
    skipped:skippedCount(state||{}),
    awaitingPeer:!!state?.pendingHandshake
  };
}
