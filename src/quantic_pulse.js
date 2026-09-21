import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import { join } from 'node:path';
import { randomBytes, createHash, createPublicKey, verify } from 'node:crypto';
import { SupabaseBridge } from './supabase_bridge.js';

const DATA_DIR=process.env.DATA_DIR||'./data';
const FILE=join(DATA_DIR,'pulse.json');
const SESSION_MS=2592000000;
const PRESENCE_LEASE_MS=12000;
const POST_TTL_MS=Math.max(60000,Number(process.env.PULSE_POST_TTL_MS||86400000));
const HANDLE_RE=/^[a-z0-9_]{3,24}$/;
const PULSE_DATABASE_URL=process.env.PULSE_DATABASE_URL||'';
let parsedMysql=null;
const rawMysql=String(process.env.MYSQL_URL||process.env.DATABASE_URL||'').trim();
if(rawMysql){
  try{
    const u=new URL(rawMysql);
    if(u.protocol==='mysql:'||u.protocol==='mariadb:'){
      parsedMysql={host:u.hostname,port:Number(u.port||3306),user:decodeURIComponent(u.username||''),password:decodeURIComponent(u.password||''),database:decodeURIComponent(String(u.pathname||'').replace(/^\//,''))};
    }
  }catch{}
}
const MYSQL={
  host:process.env.PULSE_DB_HOST||process.env.MYSQL_HOST||process.env.DB_HOST||parsedMysql?.host||'',
  port:Number(process.env.PULSE_DB_PORT||process.env.MYSQL_PORT||process.env.DB_PORT||parsedMysql?.port||3306),
  user:process.env.PULSE_DB_USER||process.env.MYSQL_USER||process.env.DB_USER||parsedMysql?.user||'',
  password:process.env.PULSE_DB_PASSWORD||process.env.MYSQL_PASSWORD||process.env.DB_PASSWORD||parsedMysql?.password||'',
  database:process.env.PULSE_DB_NAME||process.env.MYSQL_DATABASE||process.env.DB_NAME||parsedMysql?.database||''
};
const usePostgres=!!PULSE_DATABASE_URL;
const useMysql=!usePostgres&&!!(MYSQL.host&&MYSQL.user&&MYSQL.database);
const PULSE_REMOTE_STORE_URL=String(process.env.PULSE_REMOTE_STORE_URL||'').trim().replace(/\/$/,'');
const PULSE_REMOTE_STORE_TOKEN=String(process.env.PULSE_REMOTE_STORE_TOKEN||'').trim();
const useRemoteStore=Boolean(PULSE_REMOTE_STORE_URL&&PULSE_REMOTE_STORE_TOKEN.length>=32);
const supabase=new SupabaseBridge();
const useSupabase=supabase.enabled;
let pgPool=null,mysqlPool=null,writeQueue=Promise.resolve(),pulseCache=emptyStore(),pulseCacheReady=false;
let activeStorage='json';
const rate=new Map();
const identityChallenges=new Map();
const IDENTITY_AUDIENCE='quantic-pulse';
const IDENTITY_CHALLENGE_MS=120000;

function emptyStore(){return{version:3,users:{},handles:{},sessions:{},posts:{},follows:{},likes:{},reposts:{},bookmarks:{},circles:{},circleMembers:{},notifications:{},reports:{},blocks:{},conversations:{},messages:{},secureDevices:{},securePreKeys:{},securePreKeyUsed:{}}}
function id(prefix=''){return prefix+randomBytes(12).toString('hex')}
function sha(v){return createHash('sha256').update(String(v)).digest('hex')}
function now(){return new Date().toISOString()}
function clean(v,max=500){return String(v||'').replace(/\u0000/g,'').trim().slice(0,max)}
function safeHttpsUrl(v,max=1600){const value=clean(v,max);if(!value)return'';try{const u=new URL(value);return u.protocol==='https:'?u.href:''}catch{return''}}
function json(res,status,body,extra={}){res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store',...extra});res.end(JSON.stringify(body))}
async function bodyJson(req,limit=65536){let size=0,chunks=[];for await(const chunk of req){size+=chunk.length;if(size>limit)throw Object.assign(new Error('body_too_large'),{status:413});chunks.push(chunk)}if(!chunks.length)return{};try{return JSON.parse(Buffer.concat(chunks).toString('utf8'))}catch{throw Object.assign(new Error('invalid_json'),{status:400})}}
function bearer(req){return String(req.headers.authorization||'').match(/^Bearer\s+(.+)$/i)?.[1]||''}
function allowRate(req,bucket,max,windowMs){const ip=String(req.headers['x-forwarded-for']||req.socket?.remoteAddress||'unknown').split(',')[0].trim(),key=ip+':'+bucket,t=Date.now(),cur=rate.get(key);if(!cur||t-cur.start>windowMs){rate.set(key,{start:t,count:1});return true}cur.count++;return cur.count<=max}
function cleanupIdentityChallenges(){const t=Date.now();for(const[key,value]of identityChallenges)if(value.expiresAt<=t)identityChallenges.delete(key)}
function identityKeyId(publicKeyB64url){return'qid_'+createHash('sha256').update(Buffer.from(publicKeyB64url,'base64url')).digest('hex').slice(0,32)}
function issueIdentityChallenge(action,handle){
  cleanupIdentityChallenges();
  const challenge=randomBytes(32).toString('base64url'),expiresAt=Date.now()+IDENTITY_CHALLENGE_MS;
  identityChallenges.set(challenge,{action,handle,expiresAt});
  return{challenge,audience:IDENTITY_AUDIENCE,expiresAt:new Date(expiresAt).toISOString()};
}
function verifyIdentityProof(proof,{action,handle}){
  cleanupIdentityChallenges();
  if(!proof||typeof proof!=='object')return{error:'identity_proof_required'};
  const keyId=clean(proof.keyId,80),publicKey=clean(proof.publicKey,1600),payload=String(proof.payload||''),signature=clean(proof.signature,1400);
  const algorithm=clean(proof.algorithm||'ed25519',80);
  if(!keyId||!publicKey||!payload||!signature)return{error:'identity_proof_required'};
  let parsed;
  try{parsed=JSON.parse(payload)}catch{return{error:'identity_proof_invalid'}}
  const challenge=clean(parsed.challenge,4096),entry=identityChallenges.get(challenge);
  if(!entry||entry.expiresAt<=Date.now())return{error:'identity_challenge_expired'};
  identityChallenges.delete(challenge);
  if(entry.action!==action||entry.handle!==handle)return{error:'identity_challenge_mismatch'};
  if(parsed.audience!==IDENTITY_AUDIENCE||parsed.keyId!==keyId)return{error:'identity_proof_invalid'};
  if(identityKeyId(publicKey)!==keyId)return{error:'identity_proof_invalid'};
  try{
    const key=createPublicKey({key:Buffer.from(publicKey,'base64url'),type:'spki',format:'der'});
    let ok=false;
    if(algorithm==='ed25519'){
      if(key.asymmetricKeyType!=='ed25519')return{error:'identity_proof_invalid'};
      ok=verify(null,Buffer.from(payload),key,Buffer.from(signature,'base64url'));
    }else if(algorithm==='ecdsa-p256-sha256'){
      if(key.asymmetricKeyType!=='ec'||key.asymmetricKeyDetails?.namedCurve!=='prime256v1')return{error:'identity_proof_invalid'};
      ok=verify('sha256',Buffer.from(payload),{key,dsaEncoding:'ieee-p1363'},Buffer.from(signature,'base64url'));
    }else{
      return{error:'identity_algorithm_unsupported'};
    }
    if(!ok)return{error:'identity_proof_invalid'};
  }catch{return{error:'identity_proof_invalid'}}
  return{keyId,publicKey,algorithm};
}

async function pg(){
  if(!usePostgres)return null;
  if(pgPool)return pgPool;
  const mod=await import('pg');
  const connectionUrl=new URL(PULSE_DATABASE_URL);
  if(connectionUrl.searchParams.get('sslmode')==='require')connectionUrl.searchParams.set('sslmode','verify-full');
  pgPool=new mod.Pool({connectionString:connectionUrl.toString(),max:4});
  await pgPool.query('CREATE TABLE IF NOT EXISTS quantic_pulse_store (store_key VARCHAR(40) PRIMARY KEY, data JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())');
  await pgPool.query('INSERT INTO quantic_pulse_store (store_key,data) VALUES ($1,$2::jsonb) ON CONFLICT (store_key) DO NOTHING',['pulse',JSON.stringify(emptyStore())]);
  return pgPool;
}
async function pool(){
  if(!useMysql)return null;
  if(mysqlPool)return mysqlPool;
  const mysql=await import('mysql2/promise');
  mysqlPool=mysql.createPool({host:MYSQL.host,port:MYSQL.port,user:MYSQL.user,password:MYSQL.password,database:MYSQL.database,waitForConnections:true,connectionLimit:4,charset:'utf8mb4'});
  await mysqlPool.query('CREATE TABLE IF NOT EXISTS quantic_pulse_store (store_key VARCHAR(40) PRIMARY KEY, data LONGTEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)');
  await mysqlPool.query('INSERT IGNORE INTO quantic_pulse_store (store_key,data) VALUES (?,?)',['pulse',JSON.stringify(emptyStore())]);
  return mysqlPool;
}
async function ensureFile(){await mkdir(DATA_DIR,{recursive:true});try{await readFile(FILE,'utf8')}catch{await writeFile(FILE,JSON.stringify(emptyStore(),null,2))}}
async function remotePulseRequest(method='GET',body=null){
  if(!useRemoteStore)throw new Error('pulse_remote_store_not_configured');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try{
    const response=await fetch(PULSE_REMOTE_STORE_URL,{
      method,
      cache:'no-store',
      headers:{
        authorization:'Bearer '+PULSE_REMOTE_STORE_TOKEN,
        accept:'application/json',
        ...(body===null?{}:{'content-type':'application/json'})
      },
      body:body===null?undefined:JSON.stringify(body),
      signal:controller.signal
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      const error=Object.assign(new Error(data.error||('pulse_remote_http_'+response.status)),{status:response.status,data});
      throw error;
    }
    return data;
  }finally{clearTimeout(timer)}
}
async function readRemoteStore(){
  if(!useRemoteStore)return null;
  try{
    const row=await remotePulseRequest('GET');
    if(row?.payload&&typeof row.payload==='object')return{store:cacheStore(row.payload,'quantic-relay'),revision:Number(row.revision||0)};
    return{store:cacheStore(emptyStore(),'quantic-relay'),revision:Number(row?.revision||0)};
  }catch(error){
    console.error('[pulse] remote store read failed',String(error?.message||error));
    return null;
  }
}
async function mutateRemoteStore(fn){
  let out;
  writeQueue=writeQueue.catch(()=>{}).then(async()=>{
    const snapshot=await readRemoteStore();
    if(!snapshot)throw Object.assign(new Error('pulse_storage_unavailable'),{status:503});
    const store=snapshot.store;
    pruneExpiredPosts(store);
    out=await fn(store);
    pruneExpiredPosts(store);
    const saved=await remotePulseRequest('PUT',{payload:store,expectedRevision:snapshot.revision});
    cacheStore(store,'quantic-relay');
    return saved;
  });
  await writeQueue;
  return out;
}
function hasPulseData(store){return!!store&&(['users','posts','messages','circles'].some(key=>Object.keys(store[key]||{}).length>0))}
function cacheStore(store,backend){if(store&&typeof store==='object'){pulseCache=store;pulseCacheReady=true;if(backend)activeStorage=backend}return store}
async function readLocalStore(){await ensureFile();try{return JSON.parse(await readFile(FILE,'utf8'))}catch{return emptyStore()}}
async function readSupabaseStore(){
  if(!useSupabase)return null;
  try{
    const row=await supabase.readState('quantic_pulse');
    if(row?.payload&&typeof row.payload==='object')return cacheStore(row.payload,'supabase');
    const local=await readLocalStore();
    if(hasPulseData(local)){
      const saved=await supabase.writeState('quantic_pulse',local);
      if(saved?.ok)return cacheStore(local,'supabase');
    }
    return cacheStore(emptyStore(),'supabase');
  }catch(error){
    console.error('[pulse] supabase read failed',String(error?.message||error));
    return pulseCacheReady?pulseCache:null;
  }
}
async function readStore(){
  if(usePostgres){
    try{
      const p=await pg(),r=await p.query('SELECT data FROM quantic_pulse_store WHERE store_key=$1',['pulse']);
      const data=r.rows.length?r.rows[0].data:emptyStore();
      return cacheStore(typeof data==='string'?JSON.parse(data):data,'postgres');
    }catch(error){console.error('[pulse] postgres read failed',String(error?.message||error))}
  }
  if(useRemoteStore){
    const remote=await readRemoteStore();
    if(remote?.store)return remote.store;
  }
  if(useSupabase){
    const store=await readSupabaseStore();
    if(store)return store;
  }
  if(useMysql){
    try{
      const p=await pool(),[rows]=await p.query('SELECT data FROM quantic_pulse_store WHERE store_key=?',['pulse']);
      const store=rows.length?JSON.parse(rows[0].data):emptyStore();
      return cacheStore(store,'mysql');
    }catch(error){console.error('[pulse] mysql read failed',String(error?.message||error))}
  }
  if(pulseCacheReady)return pulseCache;
  if(usePostgres||useRemoteStore||useSupabase||useMysql)throw Object.assign(new Error('pulse_storage_unavailable'),{status:503});
  return cacheStore(await readLocalStore(),'json');
}
async function mutateStore(fn){
  // Explicit Pulse Postgres remains first choice.
  if(usePostgres){
    try{
      const p=await pg(),client=await p.connect();
      try{
        await client.query('BEGIN');
        const r=await client.query('SELECT data FROM quantic_pulse_store WHERE store_key=$1 FOR UPDATE',['pulse']);
        const raw=r.rows.length?r.rows[0].data:emptyStore(),store=typeof raw==='string'?JSON.parse(raw):raw;
        pruneExpiredPosts(store);
        const out=await fn(store);
        pruneExpiredPosts(store);
        await client.query('INSERT INTO quantic_pulse_store (store_key,data,updated_at) VALUES ($1,$2::jsonb,NOW()) ON CONFLICT (store_key) DO UPDATE SET data=EXCLUDED.data,updated_at=NOW()',['pulse',JSON.stringify(store)]);
        await client.query('COMMIT');
        cacheStore(store,'postgres');
        return out;
      }catch(error){await client.query('ROLLBACK');throw error}
      finally{client.release()}
    }catch(error){console.error('[pulse] postgres write failed',String(error?.message||error))}
  }

  if(useRemoteStore){
    try{return await mutateRemoteStore(fn)}
    catch(error){console.error('[pulse] remote store write failed',String(error?.message||error))}
  }

  // Supabase remains a fallback when configured and reachable.
  if(useSupabase){
    let out;
    writeQueue=writeQueue.catch(()=>{}).then(async()=>{
      let store=await readSupabaseStore();
      if(!store&&pulseCacheReady)store=pulseCache;
      if(!store)throw Object.assign(new Error('pulse_storage_unavailable'),{status:503});
      pruneExpiredPosts(store);
      out=await fn(store);
      pruneExpiredPosts(store);
      const saved=await supabase.writeState('quantic_pulse',store);
      if(!saved?.ok)throw new Error('pulse_storage_unavailable');
      cacheStore(store,'supabase');
    });
    try{await writeQueue;return out}
    catch(error){console.error('[pulse] supabase write failed',String(error?.message||error))}
  }

  if(useMysql){
    try{
      const p=await pool(),conn=await p.getConnection();
      try{
        await conn.beginTransaction();
        const[rows]=await conn.query('SELECT data FROM quantic_pulse_store WHERE store_key=? FOR UPDATE',['pulse']);
        const store=rows.length?JSON.parse(rows[0].data):(pulseCacheReady?pulseCache:emptyStore());
        pruneExpiredPosts(store);
        const out=await fn(store);
        pruneExpiredPosts(store);
        await conn.query('INSERT INTO quantic_pulse_store (store_key,data) VALUES (?,?) ON DUPLICATE KEY UPDATE data=VALUES(data)',['pulse',JSON.stringify(store)]);
        await conn.commit();
        cacheStore(store,'mysql');
        return out;
      }catch(error){await conn.rollback();throw error}
      finally{conn.release()}
    }catch(error){console.error('[pulse] mysql write failed',String(error?.message||error))}
  }

  // If a durable backend is configured but unreachable, fail closed instead of overwriting durable state with an empty ephemeral file.
  if(usePostgres||useSupabase||useMysql)throw Object.assign(new Error('pulse_storage_unavailable'),{status:503});

  // Local storage is only for development when no durable backend exists.
  let out;
  writeQueue=writeQueue.catch(()=>{}).then(async()=>{
    const store=pulseCacheReady?pulseCache:await readLocalStore();
    pruneExpiredPosts(store);
    out=await fn(store);
    pruneExpiredPosts(store);
    const tmp=FILE+'.'+process.pid+'.'+Date.now()+'.tmp';
    await writeFile(tmp,JSON.stringify(store,null,2));
    await rename(tmp,FILE);
    cacheStore(store,'json');
  });
  await writeQueue;
  return out;
}
function mapSet(map,key){if(!map[key])map[key]=[];return map[key]}
function blocked(store,a,b){return!!((store.blocks[a]||[]).includes(b)||(store.blocks[b]||[]).includes(a))}
function publicUser(user,store,viewerId=''){
  const followers=Object.values(store.follows||{}).filter(arr=>arr.includes(user.id)).length;
  return{id:user.id,handle:user.handle,displayName:user.displayName,bio:user.bio||'',avatar:user.avatar||'',verified:!!user.verified,createdAt:user.createdAt,followers,following:(store.follows[user.id]||[]).length,isFollowing:viewerId?(store.follows[viewerId]||[]).includes(user.id):false}
}
function visibleTo(store,post,viewerId=''){if(!postAlive(post))return false;if(post.circleId)return!!viewerId&&!!(store.circleMembers[post.circleId]||{})[viewerId];return!viewerId||!blocked(store,viewerId,post.authorId)}
function postView(post,store,viewerId=''){
  const author=store.users[post.authorId];if(!author)return null;
  const likes=store.likes[post.id]||[],reposts=store.reposts[post.id]||[],bookmarks=store.bookmarks[viewerId]||[];
  const replies=Object.values(store.posts).filter(p=>p.replyToId===post.id&&visibleTo(store,p,viewerId)).length;
  const q=post.quotePostId&&store.posts[post.quotePostId];
  return{id:post.id,author:publicUser(author,store,viewerId),body:post.body,createdAt:post.createdAt,expiresAt:postExpiryIso(post),replyToId:post.replyToId||null,quotePostId:post.quotePostId||null,circleId:post.circleId||null,linkUrl:post.linkUrl||'',linkTitle:post.linkTitle||'',imageUrl:post.imageUrl||'',mediaUrl:post.mediaUrl||'',mediaType:post.mediaType||'',quote:q&&visibleTo(store,q,viewerId)?{id:q.id,body:q.body,createdAt:q.createdAt,author:publicUser(store.users[q.authorId],store,viewerId)}:null,counts:{likes:likes.length,reposts:reposts.length,replies},viewer:{liked:likes.includes(viewerId),reposted:reposts.includes(viewerId),bookmarked:bookmarks.includes(post.id)}}
}
function cleanupSessions(store){const t=Date.now();for(const[h,s]of Object.entries(store.sessions||{}))if(s.expiresAt<=t)delete store.sessions[h]}
function sessionRecord(store,token,{requirePresence=true}={}){
  if(!token)return null;
  cleanupSessions(store);
  const s=store.sessions[sha(token)];
  if(!s||s.expiresAt<=Date.now())return null;
  if(requirePresence&&(!s.presenceUntil||s.presenceUntil<=Date.now()))return null;
  return s;
}
function sessionUser(store,token){
  const s=sessionRecord(store,token);
  return s&&store.users[s.userId]||null;
}
async function auth(req,store=null){
  const token=bearer(req);if(!token)return null;
  store||=await readStore();
  const s=sessionRecord(store,token),user=s&&store.users[s.userId];
  return user?{user,token,store,presenceUntil:s.presenceUntil}:null;
}
function createSession(store,userId){
  const token=randomBytes(32).toString('base64url'),t=Date.now();
  store.sessions[sha(token)]={userId,createdAt:t,expiresAt:t+SESSION_MS,presenceUntil:t+PRESENCE_LEASE_MS};
  return token;
}
function notify(store,userId,payload){if(!userId||userId===payload.actorId)return;if(!store.notifications[userId])store.notifications[userId]=[];store.notifications[userId].unshift({id:id('n_'),createdAt:now(),read:false,...payload});store.notifications[userId]=store.notifications[userId].slice(0,300)}
function conversationKey(a,b){return[a,b].sort().join(':')}
function postExpiresAt(post){
  const explicit=Date.parse(String(post?.expiresAt||''));
  if(Number.isFinite(explicit))return explicit;
  const created=Date.parse(String(post?.createdAt||''));
  return Number.isFinite(created)?created+POST_TTL_MS:0;
}
function postAlive(post,at=Date.now()){return!!post&&!post.deletedAt&&postExpiresAt(post)>at}
function postExpiryIso(post){const t=postExpiresAt(post);return t?new Date(t).toISOString():null}
function pruneExpiredPosts(store,at=Date.now()){
  const expired=new Set();
  for(const [pid,post] of Object.entries(store.posts||{})){
    if(!postAlive(post,at)){expired.add(pid);delete store.posts[pid]}
  }
  if(!expired.size)return 0;
  for(const pid of expired){delete store.likes[pid];delete store.reposts[pid]}
  for(const uid of Object.keys(store.bookmarks||{}))store.bookmarks[uid]=(store.bookmarks[uid]||[]).filter(pid=>!expired.has(pid));
  for(const uid of Object.keys(store.notifications||{}))store.notifications[uid]=(store.notifications[uid]||[]).filter(item=>!expired.has(item.objectId));
  return expired.size;
}
function messageView(message){
  if(!message)return null;
  const {expiresAt:_legacyExpiry,...view}=message;
  return view;
}


function ensureSecureState(store){
  if(!store.secureDevices||typeof store.secureDevices!=='object')store.secureDevices={};
  if(!store.securePreKeys||typeof store.securePreKeys!=='object')store.securePreKeys={};
  if(!store.securePreKeyUsed||typeof store.securePreKeyUsed!=='object')store.securePreKeyUsed={};
  return store.secureDevices;
}
function normalizeSecureTransport(transport){
  if(!transport||typeof transport!=='object')return null;
  const canonicalAddress=clean(transport.canonicalAddress,160).toLowerCase();
  const deviceId=clean(transport.deviceId,80);
  const publicKey=transport.publicKey&&typeof transport.publicKey==='object'?transport.publicKey:null;
  const relays=Array.isArray(transport.relays)?transport.relays.map(value=>clean(value,500).replace(/\/$/,'')).filter(Boolean).slice(0,8):[];
  if(!/^[a-z0-9][a-z0-9._-]{2,31}~(?:[0-9a-f]{10}|[0-9a-f]{32})@quantic$/.test(canonicalAddress))return null;
  if(!/^d-[0-9a-f]{10,32}$/.test(deviceId))return null;
  if(!publicKey||publicKey.kty!=='EC'||publicKey.crv!=='P-256'||typeof publicKey.x!=='string'||typeof publicKey.y!=='string')return null;
  for(const relay of relays){
    try{
      const url=new URL(relay);
      const local=['localhost','127.0.0.1','::1','[::1]'].includes(url.hostname);
      if(url.protocol!=='https:'&&!(url.protocol==='http:'&&local))return null;
      if(url.username||url.password||url.search||url.hash)return null;
    }catch{return null}
  }
  if(!relays.length)return null;
  return{canonicalAddress,deviceId,publicKey:{kty:'EC',crv:'P-256',x:publicKey.x,y:publicKey.y},relays:[...new Set(relays)].sort()};
}
function secureBundleMaterial({deviceId,encryptionPublicKey,signingPublicKey,transport}){
  return JSON.stringify({
    protocol:'pulse-e2ee-v1',
    deviceId:clean(deviceId,80),
    encryptionPublicKey:clean(encryptionPublicKey,160),
    signingPublicKey:clean(signingPublicKey,160),
    transport:normalizeSecureTransport(transport)
  });
}
function secureBundleHash(bundle){return sha(secureBundleMaterial(bundle))}
function validRawCurveKey(value){
  const raw=clean(value,160);
  if(!/^[A-Za-z0-9_-]{40,60}$/.test(raw))return false;
  try{return Buffer.from(raw,'base64url').length===32}catch{return false}
}
function secureDeviceView(device){
  if(!device)return null;
  return{
    deviceId:device.deviceId,
    encryptionPublicKey:device.encryptionPublicKey,
    signingPublicKey:device.signingPublicKey,
    identityKeyId:device.identityKeyId,
    registeredAt:device.registeredAt,
    transport:normalizeSecureTransport(device.transport),
    protocol:'pulse-e2ee-v1'
  };
}
function secureDevicesFor(store,userId){
  ensureSecureState(store);
  return Object.values(store.secureDevices[userId]||{}).filter(Boolean);
}
const ED25519_SPKI_PREFIX=Buffer.from('302a300506032b6570032100','hex');
function securePreKeyMaterial(record){
  const protocol=record?.protocol==='pulse-prekey-v2'?'pulse-prekey-v2':'pulse-prekey-v1';
  const material={
    protocol,
    deviceId:clean(record.deviceId,80),
    preKeyId:clean(record.preKeyId,80),
    publicKey:clean(record.publicKey,160),
    createdAt:clean(record.createdAt,80),
    expiresAt:clean(record.expiresAt,80)
  };
  if(protocol==='pulse-prekey-v2'){
    material.pqAlgorithm=clean(record.pqAlgorithm,40);
    material.pqPublicKey=clean(record.pqPublicKey,2200);
  }
  return JSON.stringify(material);
}
function verifySecurePreKey(record,device){
  if(!record||!device)return false;
  const protocol=record.protocol==='pulse-prekey-v2'?'pulse-prekey-v2':record.protocol==='pulse-prekey-v1'?'pulse-prekey-v1':'';
  const deviceId=clean(record.deviceId,80),preKeyId=clean(record.preKeyId,80),publicKey=clean(record.publicKey,160),signature=clean(record.signature,800);
  if(!protocol||deviceId!==device.deviceId||!/^[a-f0-9]{32}$/.test(preKeyId)||!validRawCurveKey(publicKey))return false;
  const created=Date.parse(String(record.createdAt||'')),expires=Date.parse(String(record.expiresAt||''));
  if(!Number.isFinite(created)||!Number.isFinite(expires)||expires<=Date.now()||expires<=created||expires-created>31*24*60*60*1000)return false;
  const normalized={
    protocol,deviceId,preKeyId,publicKey,
    createdAt:new Date(created).toISOString(),
    expiresAt:new Date(expires).toISOString()
  };
  if(protocol==='pulse-prekey-v2'){
    normalized.pqAlgorithm=clean(record.pqAlgorithm,40);
    normalized.pqPublicKey=clean(record.pqPublicKey,2200);
    if(normalized.pqAlgorithm!=='ML-KEM-768')return false;
    try{if(Buffer.from(normalized.pqPublicKey,'base64url').length!==1184)return false}catch{return false}
  }
  try{
    const sig=Buffer.from(signature,'base64url');
    if(sig.length!==64)return false;
    const raw=Buffer.from(device.signingPublicKey,'base64url');
    if(raw.length!==32)return false;
    const key=createPublicKey({key:Buffer.concat([ED25519_SPKI_PREFIX,raw]),format:'der',type:'spki'});
    return verify(null,Buffer.from(securePreKeyMaterial(normalized)),key,sig);
  }catch{return false}
}
function pruneSecurePreKeys(store,at=Date.now()){
  ensureSecureState(store);
  for(const [uid,devices] of Object.entries(store.securePreKeys)){
    for(const [deviceId,pool] of Object.entries(devices||{})){
      for(const [preKeyId,record] of Object.entries(pool||{})){
        if(Date.parse(String(record.expiresAt||''))<=at)delete pool[preKeyId];
      }
      if(!Object.keys(pool||{}).length)delete devices[deviceId];
    }
    if(!Object.keys(devices||{}).length)delete store.securePreKeys[uid];
  }
  for(const [key,expiresAt] of Object.entries(store.securePreKeyUsed||{})){
    if(Number(expiresAt)<=at)delete store.securePreKeyUsed[key];
  }
}
function securePreKeyView(record){
  return record?{
    protocol:record.protocol==='pulse-prekey-v2'?'pulse-prekey-v2':'pulse-prekey-v1',
    deviceId:record.deviceId,
    preKeyId:record.preKeyId,
    publicKey:record.publicKey,
    createdAt:record.createdAt,
    expiresAt:record.expiresAt,
    signature:record.signature,
    ...(record.protocol==='pulse-prekey-v2'?{pqAlgorithm:record.pqAlgorithm,pqPublicKey:record.pqPublicKey}:{})
  }:null;
}

function validSecureEnvelope(envelope){
  if(!envelope||typeof envelope!=='object')return false;
  if(!clean(envelope.recipientDeviceId,80)||!clean(envelope.ephemeralPublicKey,160)||!clean(envelope.salt,160)||!clean(envelope.iv,80)||!clean(envelope.ciphertext,8000)||!clean(envelope.signature,800))return false;
  if(!validRawCurveKey(envelope.ephemeralPublicKey))return false;
  try{
    if(Buffer.from(String(envelope.salt),'base64url').length!==32)return false;
    if(Buffer.from(String(envelope.iv),'base64url').length!==12)return false;
    if(Buffer.from(String(envelope.signature),'base64url').length!==64)return false;
    const cipherBytes=Buffer.from(String(envelope.ciphertext),'base64url').length;
    return cipherBytes>=16&&cipherBytes<=4096;
  }catch{return false}
}
function validSessionEnvelope(envelope){
  if(!envelope||typeof envelope!=='object'||envelope.protocol!=='pulse-session-v2')return false;
  const recipientDeviceId=clean(envelope.recipientDeviceId,80),header=envelope.header;
  if(!recipientDeviceId||!header||typeof header!=='object')return false;
  if(!clean(header.sessionId,80)||!validRawCurveKey(header.dh))return false;
  if(!Number.isSafeInteger(header.pn)||header.pn<0||header.pn>0x7fffffff)return false;
  if(!Number.isSafeInteger(header.n)||header.n<0||header.n>0x7fffffff)return false;
  if(header.handshake){
    const hs=header.handshake;
    if(hs.protocol!=='pulse-handshake-v2'||!/^[a-f0-9]{32}$/.test(clean(hs.preKeyId,80))||!validRawCurveKey(hs.ephemeralPublicKey))return false;
    if(!['classical-v2','hybrid-pq-v1'].includes(hs.profile))return false;
    if(hs.profile==='hybrid-pq-v1'){
      if(hs.pqAlgorithm!=='ML-KEM-768'||!clean(hs.pqCiphertext,2600))return false;
      try{if(Buffer.from(String(hs.pqCiphertext),'base64url').length!==1088)return false}catch{return false}
    }else if(clean(hs.pqCiphertext,2600)||clean(hs.pqAlgorithm,40))return false;
  }
  try{
    if(Buffer.from(String(envelope.iv),'base64url').length!==12)return false;
    if(Buffer.from(String(envelope.signature),'base64url').length!==64)return false;
    const cipherBytes=Buffer.from(String(envelope.ciphertext),'base64url').length;
    return cipherBytes>=16&&cipherBytes<=4096;
  }catch{return false}
}

export async function pulseInfo(){
  let connected=false,lastError=null;
  if(usePostgres){
    try{await pg();connected=true;activeStorage='postgres'}catch(error){lastError=String(error?.message||error)}
  }
  if(!connected&&useRemoteStore){
    try{
      const remote=await remotePulseRequest('GET');
      if(remote&&Number.isFinite(Number(remote.revision))){connected=true;activeStorage='quantic-relay'}
    }catch(error){lastError=String(error?.message||error)}
  }
  if(!connected&&useSupabase){
    const health=await supabase.health().catch(error=>({connected:false,last_error:String(error?.message||error)}));
    if(health.connected){connected=true;activeStorage='supabase'}else lastError=health.last_error||lastError;
  }
  if(!connected&&useMysql){
    try{await pool();connected=true;activeStorage='mysql'}catch(error){lastError=String(error?.message||error)}
  }
  if(!connected)activeStorage='json';
  return{
    schema:'quantic-pulse-health-v3',
    storage:activeStorage,
    persistent:connected,
    postgresConfigured:usePostgres,
    mysqlConfigured:useMysql,
    remoteStoreConfigured:useRemoteStore,
    supabaseConfigured:useSupabase,
    postRetentionHours:POST_TTL_MS/3600000,
    privateMessages:'persistent',
    storageError:lastError
  }
}

export async function handlePulse(req,res,url,corsHeaders={}){
  if(!url.pathname.startsWith('/api/pulse/'))return false;
  const route=url.pathname;
  try{
    if(!allowRate(req,'all',180,60000)){json(res,429,{error:'rate_limited'},corsHeaders);return true}

    if(route==='/api/pulse/health'&&req.method==='GET'){const info=await pulseInfo();json(res,200,{ok:true,service:'quantic-pulse',...info,e2ee:'pulse-e2ee-v1',sessions:'pulse-session-v2',ratchet:'dh-double-ratchet-v1',prekeys:'pulse-prekey-v2',postQuantum:'hybrid-ml-kem-768-when-supported'},corsHeaders);return true}

    if(route==='/api/pulse/secure/challenge'&&req.method==='POST'){
      const store=await readStore(),a=await auth(req,store);
      if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}
      const b=await bodyJson(req),deviceId=clean(b.deviceId,80),encryptionPublicKey=clean(b.encryptionPublicKey,160),signingPublicKey=clean(b.signingPublicKey,160),transport=normalizeSecureTransport(b.transport);
      if(!deviceId||!validRawCurveKey(encryptionPublicKey)||!validRawCurveKey(signingPublicKey)){json(res,400,{error:'secure_device_invalid'},corsHeaders);return true}
      const bundleHash=secureBundleHash({deviceId,encryptionPublicKey,signingPublicKey,transport});
      json(res,200,{...issueIdentityChallenge('secure_device',bundleHash),bundleHash,protocol:'pulse-e2ee-v1'},corsHeaders);return true
    }

    if(route==='/api/pulse/secure/devices'&&req.method==='POST'){
      const b=await bodyJson(req),deviceId=clean(b.deviceId,80),encryptionPublicKey=clean(b.encryptionPublicKey,160),signingPublicKey=clean(b.signingPublicKey,160),transport=normalizeSecureTransport(b.transport);
      if(!deviceId||!validRawCurveKey(encryptionPublicKey)||!validRawCurveKey(signingPublicKey)||!transport){json(res,400,{error:'secure_device_invalid'},corsHeaders);return true}
      const bundleHash=secureBundleHash({deviceId,encryptionPublicKey,signingPublicKey,transport});
      const out=await mutateStore(store=>{
        const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};
        const identity=verifyIdentityProof(b.identityProof,{action:'secure_device',handle:bundleHash});
        if(identity.error)return identity;
        if(identity.keyId!==user.identityKeyId||identity.publicKey!==user.identityPublicKey)return{error:'identity_mismatch'};
        ensureSecureState(store);
        const devices=store.secureDevices[user.id]||(store.secureDevices[user.id]={});
        const existing=devices[deviceId];
        if(existing&&(existing.encryptionPublicKey!==encryptionPublicKey||existing.signingPublicKey!==signingPublicKey))return{error:'secure_device_conflict'};
        devices[deviceId]={
          deviceId,encryptionPublicKey,signingPublicKey,identityKeyId:identity.keyId,transport,
          registeredAt:existing?.registeredAt||now(),lastSeenAt:now(),protocol:'pulse-e2ee-v1'
        };
        return{ok:true,device:secureDeviceView(devices[deviceId])};
      });
      json(res,out.error?(out.error==='unauthorized'?401:out.error==='secure_device_conflict'?409:400):200,out,corsHeaders);return true
    }

    if(route==='/api/pulse/secure/devices'&&req.method==='GET'){
      const store=await readStore(),a=await auth(req,store);
      if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}
      ensureSecureState(store);pruneSecurePreKeys(store);
      const devices=secureDevicesFor(store,a.user.id).map(device=>({...secureDeviceView(device),preKeyCount:Object.keys(store.securePreKeys[a.user.id]?.[device.deviceId]||{}).length}));
      json(res,200,{protocol:'pulse-e2ee-v1',prekeys:'pulse-prekey-v1',devices},corsHeaders);return true
    }

    if(route==='/api/pulse/secure/prekeys'&&req.method==='POST'){
      const b=await bodyJson(req),deviceId=clean(b.deviceId,80),records=Array.isArray(b.records)?b.records:[];
      if(!deviceId||records.length<1||records.length>64){json(res,400,{error:'secure_prekeys_invalid'},corsHeaders);return true}
      const out=await mutateStore(store=>{
        const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};
        ensureSecureState(store);pruneSecurePreKeys(store);
        const device=store.secureDevices[user.id]?.[deviceId];
        if(!device)return{error:'secure_device_required'};
        const pool=((store.securePreKeys[user.id]||(store.securePreKeys[user.id]={}))[deviceId]||(store.securePreKeys[user.id][deviceId]={}));
        let accepted=0;
        for(const input of records){
          const record={
            protocol:input.protocol==='pulse-prekey-v2'?'pulse-prekey-v2':'pulse-prekey-v1',
            deviceId,
            preKeyId:clean(input.preKeyId,80),
            publicKey:clean(input.publicKey,160),
            createdAt:Number.isFinite(Date.parse(String(input.createdAt||'')))?new Date(input.createdAt).toISOString():'',
            expiresAt:Number.isFinite(Date.parse(String(input.expiresAt||'')))?new Date(input.expiresAt).toISOString():'',
            signature:clean(input.signature,800),
            ...(input.protocol==='pulse-prekey-v2'?{
              pqAlgorithm:clean(input.pqAlgorithm,40),
              pqPublicKey:clean(input.pqPublicKey,2200)
            }:{})
          };
          if(!verifySecurePreKey(record,device))return{error:'secure_prekey_signature_invalid'};
          const usedKey=user.id+':'+deviceId+':'+record.preKeyId;
          if(store.securePreKeyUsed[usedKey])continue;
          pool[record.preKeyId]=record;accepted++;
        }
        return{ok:true,accepted,available:Object.keys(pool).length,protocol:'pulse-prekey-v2'};
      });
      json(res,out.error?(out.error==='unauthorized'?401:400):200,out,corsHeaders);return true
    }

    if(route==='/api/pulse/secure/prekeys/status'&&req.method==='GET'){
      const store=await readStore(),a=await auth(req,store);
      if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}
      ensureSecureState(store);pruneSecurePreKeys(store);
      const devices={};
      for(const device of secureDevicesFor(store,a.user.id))devices[device.deviceId]=Object.keys(store.securePreKeys[a.user.id]?.[device.deviceId]||{}).length;
      json(res,200,{protocol:'pulse-prekey-v2',devices},corsHeaders);return true
    }

    if(route==='/api/pulse/secure/prekeys/claim'&&req.method==='POST'){
      const b=await bodyJson(req),handle=clean(b.handle,24).toLowerCase().replace(/^@/,''),deviceId=clean(b.deviceId,80);
      const out=await mutateStore(store=>{
        const user=sessionUser(store,bearer(req)),targetId=store.handles[handle];
        if(!user)return{error:'unauthorized'};if(!targetId)return{error:'not_found'};if(blocked(store,user.id,targetId))return{error:'blocked'};
        ensureSecureState(store);pruneSecurePreKeys(store);
        const targetDevice=store.secureDevices[targetId]?.[deviceId];
        if(!targetDevice)return{error:'secure_device_required'};
        const pool=store.securePreKeys[targetId]?.[deviceId]||{};
        const record=Object.values(pool).sort((a,b)=>{
          const rank=value=>value?.protocol==='pulse-prekey-v2'?2:1;
          return rank(b)-rank(a)||Date.parse(a.createdAt)-Date.parse(b.createdAt);
        })[0];
        if(!record)return{error:'secure_prekey_unavailable'};
        delete pool[record.preKeyId];
        store.securePreKeyUsed[targetId+':'+deviceId+':'+record.preKeyId]=Date.parse(record.expiresAt)||Date.now()+31*24*60*60*1000;
        return{protocol:'pulse-prekey-v2',handle,device:secureDeviceView(targetDevice),preKey:securePreKeyView(record)};
      });
      json(res,out.error?(out.error==='unauthorized'?401:out.error==='not_found'?404:out.error==='secure_prekey_unavailable'?404:400):200,out,corsHeaders);return true
    }

    let secureMatch=route.match(/^\/api\/pulse\/secure\/bundle\/([a-z0-9_]{3,24})$/);
    if(secureMatch&&req.method==='GET'){
      const store=await readStore(),a=await auth(req,store);
      if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}
      const uid=store.handles[secureMatch[1]],user=uid&&store.users[uid];
      if(!user||blocked(store,a.user.id,uid)){json(res,404,{error:'not_found'},corsHeaders);return true}
      ensureSecureState(store);pruneSecurePreKeys(store);
      const devices=secureDevicesFor(store,uid).map(device=>({...secureDeviceView(device),preKeyCount:Object.keys(store.securePreKeys[uid]?.[device.deviceId]||{}).length}));
      json(res,200,{protocol:'pulse-e2ee-v1',sessions:'pulse-session-v2',prekeys:'pulse-prekey-v2',handle:user.handle,identityKeyId:user.identityKeyId||'',devices},corsHeaders);return true
    }

    if(route==='/api/pulse/auth/challenge'&&req.method==='POST'){
      if(!allowRate(req,'identity_challenge',40,60000)){json(res,429,{error:'rate_limited'},corsHeaders);return true}
      const b=await bodyJson(req),action=b.action==='register'?'register':'login',handle=action==='register'?clean(b.handle,24).toLowerCase().replace(/^@/,''):'';
      if(action==='register'&&!HANDLE_RE.test(handle)){json(res,400,{error:'invalid_handle'},corsHeaders);return true}
      json(res,200,issueIdentityChallenge(action,handle),corsHeaders);return true
    }

    if(route==='/api/pulse/auth/presence/challenge'&&req.method==='POST'){
      if(!allowRate(req,'identity_presence',40,60000)){json(res,429,{error:'rate_limited'},corsHeaders);return true}
      const token=bearer(req),store=await readStore(),session=sessionRecord(store,token,{requirePresence:false}),user=session&&store.users[session.userId];
      if(!user){json(res,401,{error:'unauthorized'},corsHeaders);return true}
      json(res,200,issueIdentityChallenge('presence',user.identityKeyId||''),corsHeaders);return true
    }

    if(route==='/api/pulse/auth/presence'&&req.method==='POST'){
      const token=bearer(req),store=await readStore(),session=sessionRecord(store,token,{requirePresence:false}),user=session&&store.users[session.userId];
      if(!user){json(res,401,{error:'unauthorized'},corsHeaders);return true}
      const b=await bodyJson(req),identity=verifyIdentityProof(b.identityProof,{action:'presence',handle:user.identityKeyId||''});
      if(identity.error){json(res,401,{error:identity.error},corsHeaders);return true}
      if(identity.keyId!==user.identityKeyId||identity.publicKey!==user.identityPublicKey){json(res,401,{error:'identity_mismatch'},corsHeaders);return true}
      const presenceUntil=Date.now()+PRESENCE_LEASE_MS;
      await mutateStore(nextStore=>{
        const next=sessionRecord(nextStore,token,{requirePresence:false});
        if(next&&next.userId===user.id)next.presenceUntil=presenceUntil;
        return{ok:!!next};
      });
      json(res,200,{ok:true,presenceUntil:new Date(presenceUntil).toISOString()},corsHeaders);return true
    }

    if(route==='/api/pulse/auth/register'&&req.method==='POST'){
      if(!allowRate(req,'register',8,3600000)){json(res,429,{error:'rate_limited'},corsHeaders);return true}
      const b=await bodyJson(req),handle=clean(b.handle,24).toLowerCase().replace(/^@/,''),displayName=clean(b.displayName,50);
      if(!HANDLE_RE.test(handle)){json(res,400,{error:'invalid_handle'},corsHeaders);return true}
      if(displayName.length<2){json(res,400,{error:'invalid_display_name'},corsHeaders);return true}
      const identity=verifyIdentityProof(b.identityProof,{action:'register',handle});
      if(identity.error){json(res,401,{error:identity.error},corsHeaders);return true}
      const out=await mutateStore(store=>{
        if(store.handles[handle])return{error:'handle_taken'};
        if(Object.values(store.users).some(user=>user.identityKeyId===identity.keyId))return{error:'identity_already_linked'};
        const uid=id('u_');
        store.users[uid]={id:uid,handle,displayName,bio:'',avatar:'',verified:false,identityKeyId:identity.keyId,identityPublicKey:identity.publicKey,createdAt:now(),updatedAt:now()};
        store.handles[handle]=uid;store.follows[uid]=[];store.blocks[uid]=[];store.bookmarks[uid]=[];
        const token=createSession(store,uid);return{token,user:publicUser(store.users[uid],store,uid)}
      });
      json(res,out.error?(out.error==='identity_already_linked'?409:409):201,out,corsHeaders);return true
    }

    if(route==='/api/pulse/auth/login'&&req.method==='POST'){
      if(!allowRate(req,'login',20,900000)){json(res,429,{error:'rate_limited'},corsHeaders);return true}
      const b=await bodyJson(req);
      const identity=verifyIdentityProof(b.identityProof,{action:'login',handle:''});
      if(identity.error){json(res,401,{error:identity.error},corsHeaders);return true}
      const out=await mutateStore(store=>{
        let user=Object.values(store.users).find(user=>user.identityKeyId===identity.keyId);
        if(!user&&b.provision===true){
          const displayName=clean(b.displayName,50)||'Membre Quantic';
          const base=displayName.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9_]+/g,'_').replace(/^_+|_+$/g,'').slice(0,16)||'quantic';
          let handle=base.length>=3?base:'quantic';
          if(store.handles[handle])handle=(handle.slice(0,15)+'_'+identity.keyId.slice(-6)).slice(0,24);
          const uid=id('u_');
          user={id:uid,handle,displayName,bio:'',avatar:'',verified:false,identityKeyId:identity.keyId,identityPublicKey:identity.publicKey,createdAt:now(),updatedAt:now()};
          store.users[uid]=user;store.handles[handle]=uid;store.follows[uid]=[];store.blocks[uid]=[];store.bookmarks[uid]=[];
        }
        if(!user)return{error:'identity_not_registered'};
        if(user.identityPublicKey&&user.identityPublicKey!==identity.publicKey)return{error:'identity_mismatch'};
        const token=createSession(store,user.id);return{token,user:publicUser(user,store,user.id)}
      });
      json(res,out.error?401:200,out,corsHeaders);return true
    }

    if(route==='/api/pulse/auth/logout'&&req.method==='POST'){const token=bearer(req);if(token)await mutateStore(store=>{delete store.sessions[sha(token)]});json(res,200,{ok:true},corsHeaders);return true}

    if(route==='/api/pulse/me'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store);if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}json(res,200,{user:publicUser(a.user,store,a.user.id)},corsHeaders);return true}

    if(route==='/api/pulse/me'&&req.method==='PATCH'){
      const b=await bodyJson(req),out=await mutateStore(store=>{const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};const displayName=clean(b.displayName??user.displayName,50),bio=clean(b.bio??user.bio,240),avatar=clean(b.avatar??user.avatar,500);if(displayName.length<2)return{error:'invalid_display_name'};user.displayName=displayName;user.bio=bio;user.avatar=avatar;user.updatedAt=now();return{user:publicUser(user,store,user.id)}});
      json(res,out.error?(out.error==='unauthorized'?401:400):200,out,corsHeaders);return true
    }

    if(route==='/api/pulse/feed'&&req.method==='GET'){
      const store=await readStore(),a=await auth(req,store),viewer=a?.user.id||'',mode=url.searchParams.get('mode')==='discover'?'discover':'following',limit=Math.max(1,Math.min(50,Number(url.searchParams.get('limit')||30)));
      let posts=Object.values(store.posts).filter(p=>visibleTo(store,p,viewer)&&!p.replyToId);
      if(mode==='following'&&viewer){const allowed=new Set([viewer,...(store.follows[viewer]||[])]);posts=posts.filter(p=>allowed.has(p.authorId))}
      if(mode==='discover')posts.sort((x,y)=>{const score=p=>(store.likes[p.id]?.length||0)*2+(store.reposts[p.id]?.length||0)*3+Math.max(0,48-(Date.now()-Date.parse(p.createdAt))/3600000);return score(y)-score(x)});else posts.sort((x,y)=>Date.parse(y.createdAt)-Date.parse(x.createdAt));
      json(res,200,{posts:posts.slice(0,limit).map(p=>postView(p,store,viewer)).filter(Boolean)},corsHeaders);return true
    }

    if(route==='/api/pulse/posts'&&req.method==='POST'){
      if(!allowRate(req,'post',24,60000)){json(res,429,{error:'rate_limited'},corsHeaders);return true}
      const b=await bodyJson(req),text=clean(b.body,420);if(!text){json(res,400,{error:'empty_post'},corsHeaders);return true}
      const linkUrl=safeHttpsUrl(b.linkUrl),linkTitle=clean(b.linkTitle,240),imageUrl=safeHttpsUrl(b.imageUrl),mediaUrl=safeHttpsUrl(b.mediaUrl),mediaType=clean(b.mediaType,20)==='gif'?'gif':'';
      const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};const replyToId=clean(b.replyToId,80)||null,quotePostId=clean(b.quotePostId,80)||null,circleId=clean(b.circleId,80)||null;const replyTarget=replyToId?store.posts[replyToId]:null,quoteTarget=quotePostId?store.posts[quotePostId]:null;if(replyToId&&(!replyTarget||!visibleTo(store,replyTarget,user.id)))return{error:'reply_target_not_found'};if(quotePostId&&(!quoteTarget||!visibleTo(store,quoteTarget,user.id)))return{error:'quote_target_not_found'};if(circleId&&!(store.circleMembers[circleId]||{})[user.id])return{error:'circle_forbidden'};if(replyTarget?.circleId&&circleId!==replyTarget.circleId)return{error:'reply_target_private'};if(quoteTarget?.circleId&&circleId!==quoteTarget.circleId)return{error:'quote_target_private'};const pid=id('p_'),createdAt=now(),post={id:pid,authorId:user.id,body:text,createdAt,expiresAt:new Date(Date.parse(createdAt)+POST_TTL_MS).toISOString(),replyToId,quotePostId,circleId,linkUrl,linkTitle,imageUrl,mediaUrl,mediaType,deletedAt:null};store.posts[pid]=post;if(replyToId)notify(store,store.posts[replyToId].authorId,{actorId:user.id,type:'reply',objectId:pid});if(quotePostId)notify(store,store.posts[quotePostId].authorId,{actorId:user.id,type:'quote',objectId:pid});return{post:postView(post,store,user.id)}});
      json(res,out.error?(out.error==='unauthorized'?401:/_target_(?:not_found|private)$/.test(out.error)?404:400):201,out,corsHeaders);return true
    }

    let m=route.match(/^\/api\/pulse\/posts\/([^/]+)$/);
    if(m&&req.method==='GET'){const store=await readStore(),a=await auth(req,store),post=store.posts[m[1]];if(!post||!visibleTo(store,post,a?.user.id||'')){json(res,404,{error:'not_found'},corsHeaders);return true}json(res,200,{post:postView(post,store,a?.user.id||'')},corsHeaders);return true}
    if(m&&req.method==='DELETE'){const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req)),post=store.posts[m[1]];if(!user)return{error:'unauthorized'};if(!post)return{error:'not_found'};if(post.authorId!==user.id)return{error:'forbidden'};post.deletedAt=now();return{ok:true}});json(res,out.error?(out.error==='unauthorized'?401:out.error==='forbidden'?403:404):200,out,corsHeaders);return true}

    m=route.match(/^\/api\/pulse\/posts\/([^/]+)\/replies$/);
    if(m&&req.method==='GET'){const store=await readStore(),a=await auth(req,store),viewer=a?.user.id||'',parent=store.posts[m[1]];if(!parent||!visibleTo(store,parent,viewer)){json(res,404,{error:'not_found'},corsHeaders);return true}const posts=Object.values(store.posts).filter(p=>p.replyToId===m[1]&&visibleTo(store,p,viewer)).sort((x,y)=>Date.parse(x.createdAt)-Date.parse(y.createdAt));json(res,200,{posts:posts.map(p=>postView(p,store,viewer)).filter(Boolean)},corsHeaders);return true}

    m=route.match(/^\/api\/pulse\/posts\/([^/]+)\/(like|repost|bookmark)$/);
    if(m&&req.method==='POST'){const postId=m[1],action=m[2],out=await mutateStore(store=>{const user=sessionUser(store,bearer(req)),post=store.posts[postId];if(!user)return{error:'unauthorized'};if(!post||!visibleTo(store,post,user.id))return{error:'not_found'};const map=action==='like'?store.likes:action==='repost'?store.reposts:store.bookmarks,key=action==='bookmark'?user.id:postId,arr=mapSet(map,key),target=action==='bookmark'?postId:user.id,i=arr.indexOf(target),active=i<0;if(active)arr.push(target);else arr.splice(i,1);if(active&&action!=='bookmark')notify(store,post.authorId,{actorId:user.id,type:action,objectId:post.id});return{ok:true,active,post:postView(post,store,user.id)}});json(res,out.error?(out.error==='unauthorized'?401:404):200,out,corsHeaders);return true}

    m=route.match(/^\/api\/pulse\/users\/([a-z0-9_]{3,24})$/);
    if(m&&req.method==='GET'){const store=await readStore(),a=await auth(req,store),uid=store.handles[m[1]],user=uid&&store.users[uid];if(!user){json(res,404,{error:'not_found'},corsHeaders);return true}const posts=Object.values(store.posts).filter(p=>p.authorId===uid&&!p.replyToId&&visibleTo(store,p,a?.user.id||'')).sort((x,y)=>Date.parse(y.createdAt)-Date.parse(x.createdAt)).slice(0,40);json(res,200,{user:publicUser(user,store,a?.user.id||''),posts:posts.map(p=>postView(p,store,a?.user.id||''))},corsHeaders);return true}

    m=route.match(/^\/api\/pulse\/users\/([a-z0-9_]{3,24})\/follow$/);
    if(m&&req.method==='POST'){const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req)),targetId=store.handles[m[1]];if(!user)return{error:'unauthorized'};if(!targetId)return{error:'not_found'};if(targetId===user.id)return{error:'self_follow'};const arr=mapSet(store.follows,user.id),i=arr.indexOf(targetId),active=i<0;if(active)arr.push(targetId);else arr.splice(i,1);if(active)notify(store,targetId,{actorId:user.id,type:'follow',objectId:user.id});return{ok:true,active,user:publicUser(store.users[targetId],store,user.id)}});json(res,out.error?(out.error==='unauthorized'?401:out.error==='not_found'?404:400):200,out,corsHeaders);return true}

    m=route.match(/^\/api\/pulse\/users\/([a-z0-9_]{3,24})\/block$/);
    if(m&&req.method==='POST'){const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req)),targetId=store.handles[m[1]];if(!user)return{error:'unauthorized'};if(!targetId)return{error:'not_found'};if(targetId===user.id)return{error:'self_block'};const arr=mapSet(store.blocks,user.id),i=arr.indexOf(targetId),active=i<0;if(active)arr.push(targetId);else arr.splice(i,1);if(active){store.follows[user.id]=(store.follows[user.id]||[]).filter(x=>x!==targetId);store.follows[targetId]=(store.follows[targetId]||[]).filter(x=>x!==user.id)}return{ok:true,active}});json(res,out.error?(out.error==='unauthorized'?401:out.error==='not_found'?404:400):200,out,corsHeaders);return true}

    if(route==='/api/pulse/search'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store),viewer=a?.user.id||'',q=clean(url.searchParams.get('q'),80).toLowerCase();if(q.length<2){json(res,200,{users:[],posts:[]},corsHeaders);return true}const users=Object.values(store.users).filter(u=>!blocked(store,viewer,u.id)&&[u.handle,u.displayName,u.bio||''].join(' ').toLowerCase().includes(q)).slice(0,12).map(u=>publicUser(u,store,viewer)),posts=Object.values(store.posts).filter(p=>visibleTo(store,p,viewer)&&p.body.toLowerCase().includes(q)).sort((x,y)=>Date.parse(y.createdAt)-Date.parse(x.createdAt)).slice(0,30).map(p=>postView(p,store,viewer));json(res,200,{users,posts},corsHeaders);return true}

    if(route==='/api/pulse/circles'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store),viewer=a?.user.id||'',circles=Object.values(store.circles).filter(c=>c.visibility==='public'||(store.circleMembers[c.id]||{})[viewer]).map(c=>({...c,memberCount:Object.keys(store.circleMembers[c.id]||{}).length,joined:!!(store.circleMembers[c.id]||{})[viewer]})).sort((x,y)=>Date.parse(y.createdAt)-Date.parse(x.createdAt));json(res,200,{circles},corsHeaders);return true}

    if(route==='/api/pulse/circles'&&req.method==='POST'){const b=await bodyJson(req),out=await mutateStore(store=>{const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};const name=clean(b.name,60),description=clean(b.description,240),visibility=b.visibility==='private'?'private':'public';if(name.length<3)return{error:'invalid_name'};const cid=id('c_'),circle={id:cid,ownerId:user.id,name,description,visibility,createdAt:now()};store.circles[cid]=circle;store.circleMembers[cid]={[user.id]:'owner'};return{circle:{...circle,memberCount:1,joined:true}}});json(res,out.error?(out.error==='unauthorized'?401:400):201,out,corsHeaders);return true}

    m=route.match(/^\/api\/pulse\/circles\/([^/]+)\/join$/);
    if(m&&req.method==='POST'){const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req)),circle=store.circles[m[1]];if(!user)return{error:'unauthorized'};if(!circle)return{error:'not_found'};if(circle.visibility==='private')return{error:'invite_required'};const members=store.circleMembers[circle.id]||(store.circleMembers[circle.id]={}),active=!members[user.id];if(active)members[user.id]='member';else if(user.id!==circle.ownerId)delete members[user.id];return{ok:true,active,memberCount:Object.keys(members).length}});json(res,out.error?(out.error==='unauthorized'?401:out.error==='not_found'?404:403):200,out,corsHeaders);return true}

    if(route==='/api/pulse/notifications'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store);if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}const items=(store.notifications[a.user.id]||[]).slice(0,100).map(n=>({...n,actor:store.users[n.actorId]?publicUser(store.users[n.actorId],store,a.user.id):null}));json(res,200,{notifications:items},corsHeaders);return true}

    if(route==='/api/pulse/notifications/read'&&req.method==='POST'){const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};(store.notifications[user.id]||[]).forEach(n=>n.read=true);return{ok:true}});json(res,out.error?401:200,out,corsHeaders);return true}

    if(route==='/api/pulse/me/bookmarks'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store);if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}const posts=(store.bookmarks[a.user.id]||[]).map(pid=>store.posts[pid]).filter(p=>visibleTo(store,p,a.user.id)).map(p=>postView(p,store,a.user.id));json(res,200,{posts},corsHeaders);return true}

    if(route==='/api/pulse/report'&&req.method==='POST'){const b=await bodyJson(req),out=await mutateStore(store=>{const user=sessionUser(store,bearer(req));if(!user)return{error:'unauthorized'};const targetType=['post','user'].includes(b.targetType)?b.targetType:'post',targetId=clean(b.targetId,80),reason=clean(b.reason,240);if(!targetId||reason.length<3)return{error:'invalid_report'};const rid=id('r_');store.reports[rid]={id:rid,reporterId:user.id,targetType,targetId,reason,status:'open',createdAt:now()};return{ok:true,id:rid}});json(res,out.error?(out.error==='unauthorized'?401:400):201,out,corsHeaders);return true}

    if(route==='/api/pulse/conversations'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store);if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}const list=Object.entries(store.conversations).filter(([,c])=>c.members.includes(a.user.id)).map(([key,c])=>{const otherId=c.members.find(x=>x!==a.user.id),other=store.users[otherId],messages=(c.messageIds||[]).map(mid=>store.messages[mid]).filter(Boolean),last=messages.length?messages[messages.length-1]:null;return{key,user:other?publicUser(other,store,a.user.id):null,lastMessage:last?{body:last.protocol==='pulse-e2ee-v1'?'':(last.body||''),encrypted:last.protocol==='pulse-e2ee-v1',createdAt:last.createdAt,senderId:last.senderId}:null}}).filter(item=>item.user).sort((x,y)=>Date.parse(y.lastMessage?.createdAt||0)-Date.parse(x.lastMessage?.createdAt||0));json(res,200,{conversations:list,messageMode:'persistent',encryption:'end-to-end'},corsHeaders);return true}

    if(route==='/api/pulse/messages'&&req.method==='POST'){
      const b=await bodyJson(req),handle=clean(b.handle,24).toLowerCase().replace(/^@/,''),protocol=clean(b.protocol,40),clientMessageId=clean(b.clientMessageId,80),senderDeviceId=clean(b.senderDeviceId,80),sentAt=clean(b.sentAt,80);
      const supported=protocol==='pulse-e2ee-v1'||protocol==='pulse-session-v2';
      if(!supported||!clientMessageId||!senderDeviceId||!Array.isArray(b.envelopes)||!b.envelopes.length){json(res,400,{error:'e2ee_required'},corsHeaders);return true}
      const validEnvelope=protocol==='pulse-session-v2'?validSessionEnvelope:validSecureEnvelope;
      if(b.envelopes.length>24||b.envelopes.some(envelope=>!validEnvelope(envelope))){json(res,400,{error:'secure_envelope_invalid'},corsHeaders);return true}
      const out=await mutateStore(store=>{
        const user=sessionUser(store,bearer(req)),targetId=store.handles[handle];if(!user)return{error:'unauthorized'};if(!targetId)return{error:'not_found'};if(targetId===user.id)return{error:'self_message'};if(blocked(store,user.id,targetId))return{error:'blocked'};
        ensureSecureState(store);
        const senderDevice=store.secureDevices[user.id]?.[senderDeviceId];
        if(!senderDevice)return{error:'secure_device_required'};
        if(Object.values(store.messages||{}).some(message=>message.clientMessageId===clientMessageId&&message.senderId===user.id))return{error:'duplicate_message'};
        const allowedDevices=new Set([...secureDevicesFor(store,targetId).map(device=>device.deviceId),...secureDevicesFor(store,user.id).map(device=>device.deviceId)]);
        if(!secureDevicesFor(store,targetId).length)return{error:'secure_recipient_unavailable'};
        if(b.envelopes.some(envelope=>!allowedDevices.has(clean(envelope.recipientDeviceId,80))))return{error:'secure_envelope_recipient_invalid'};
        const key=conversationKey(user.id,targetId),conv=store.conversations[key]||(store.conversations[key]={members:[user.id,targetId],messageIds:[],createdAt:now()}),mid=id('m_'),createdAt=sentAt&&Number.isFinite(Date.parse(sentAt))?new Date(sentAt).toISOString():now();
        const envelopes=protocol==='pulse-session-v2'
          ? b.envelopes.map(envelope=>({
              protocol:'pulse-session-v2',
              recipientDeviceId:clean(envelope.recipientDeviceId,80),
              header:{
                sessionId:clean(envelope.header.sessionId,80),
                dh:clean(envelope.header.dh,160),
                pn:Number(envelope.header.pn),
                n:Number(envelope.header.n),
                ...(envelope.header.handshake?{handshake:{
                  protocol:'pulse-handshake-v2',
                  preKeyId:clean(envelope.header.handshake.preKeyId,80),
                  ephemeralPublicKey:clean(envelope.header.handshake.ephemeralPublicKey,160),
                  profile:clean(envelope.header.handshake.profile,40),
                  pqAlgorithm:clean(envelope.header.handshake.pqAlgorithm,40),
                  pqCiphertext:clean(envelope.header.handshake.pqCiphertext,2600)
                }}:{})
              },
              iv:clean(envelope.iv,80),
              ciphertext:clean(envelope.ciphertext,8000),
              signature:clean(envelope.signature,800)
            }))
          : b.envelopes.map(envelope=>({
              recipientDeviceId:clean(envelope.recipientDeviceId,80),
              ephemeralPublicKey:clean(envelope.ephemeralPublicKey,160),
              salt:clean(envelope.salt,160),
              iv:clean(envelope.iv,80),
              ciphertext:clean(envelope.ciphertext,8000),
              signature:clean(envelope.signature,800)
            }));
        const msg={id:mid,clientMessageId,conversationKey:key,senderId:user.id,recipientId:targetId,senderDeviceId,protocol,envelopes,createdAt,readAt:null};
        store.messages[mid]=msg;conv.messageIds.push(mid);conv.messageIds=conv.messageIds.slice(-1000);
        notify(store,targetId,{actorId:user.id,type:'message',objectId:mid});
        return{message:{id:mid,clientMessageId,protocol:msg.protocol,createdAt,senderId:user.id,recipientId:targetId,senderDeviceId}};
      });
      json(res,out.error?(out.error==='unauthorized'?401:out.error==='not_found'?404:out.error==='duplicate_message'?409:400):201,out,corsHeaders);return true
    }

    m=route.match(/^\/api\/pulse\/messages\/([a-z0-9_]{3,24})$/);
    if(m&&req.method==='GET'){const out=await mutateStore(store=>{const user=sessionUser(store,bearer(req)),targetId=store.handles[m[1]];if(!user)return{error:'unauthorized'};if(!targetId)return{error:'not_found'};const key=conversationKey(user.id,targetId),conv=store.conversations[key],ids=conv?.messageIds||[],messages=ids.map(mid=>store.messages[mid]).filter(Boolean);messages.forEach(msg=>{if(msg.recipientId===user.id&&!msg.readAt)msg.readAt=now()});const safeMessages=messages.map(msg=>{if(!['pulse-e2ee-v1','pulse-session-v2'].includes(msg.protocol))return messageView(msg);const senderDevice=store.secureDevices?.[msg.senderId]?.[msg.senderDeviceId];return{id:msg.id,clientMessageId:msg.clientMessageId,protocol:msg.protocol,senderId:msg.senderId,recipientId:msg.recipientId,senderDeviceId:msg.senderDeviceId,createdAt:msg.createdAt,readAt:msg.readAt,envelopes:msg.envelopes||[],senderDevice:secureDeviceView(senderDevice)}});return{user:publicUser(store.users[targetId],store,user.id),messages:safeMessages,messageMode:'persistent',encryption:'end-to-end'}});json(res,out.error?(out.error==='unauthorized'?401:404):200,out,corsHeaders);return true}

    if(route==='/api/pulse/export'&&req.method==='GET'){const store=await readStore(),a=await auth(req,store);if(!a){json(res,401,{error:'unauthorized'},corsHeaders);return true}const uid=a.user.id,data={user:publicUser(a.user,store,uid),posts:Object.values(store.posts).filter(p=>p.authorId===uid),follows:store.follows[uid]||[],likes:Object.entries(store.likes).filter(([,ids])=>ids.includes(uid)).map(([pid])=>pid),bookmarks:store.bookmarks[uid]||[],circles:Object.values(store.circles).filter(c=>(store.circleMembers[c.id]||{})[uid]),notifications:store.notifications[uid]||[],messages:Object.values(store.messages).filter(msg=>msg.senderId===uid||msg.recipientId===uid).map(messageView),secureDevices:secureDevicesFor(store,uid).map(secureDeviceView),securePreKeyCounts:Object.fromEntries(secureDevicesFor(store,uid).map(device=>[device.deviceId,Object.keys(store.securePreKeys?.[uid]?.[device.deviceId]||{}).length]))};json(res,200,{exportedAt:now(),data},corsHeaders);return true}

    json(res,404,{error:'not_found'},corsHeaders);return true
  }catch(e){console.error('[pulse]',e);const raw=String(e?.message||'internal_error');const error=/fetch failed|ECONN|ENOTFOUND|ETIMEDOUT|storage_unavailable/i.test(raw)?'pulse_storage_unavailable':raw;json(res,e.status||503,{error},corsHeaders);return true}
}

if(usePostgres)pg().catch(e=>console.error('[pulse] postgres init failed',e));
else if(useRemoteStore)remotePulseRequest('GET').catch(e=>console.error('[pulse] remote store init failed',e?.message||e));
else if(useSupabase)supabase.health().then(h=>{if(!h.connected)console.error('[pulse] supabase init failed',h.last_error)}).catch(e=>console.error('[pulse] supabase init failed',e));
else if(useMysql)pool().catch(e=>console.error('[pulse] mysql init failed',e));
else ensureFile().catch(e=>console.error('[pulse] file init failed',e));

const purgeExpiredPulsePosts=()=>mutateStore(store=>({pruned:pruneExpiredPosts(store)})).catch(error=>console.error('[pulse] post expiry purge failed',String(error?.message||error)));
setTimeout(purgeExpiredPulsePosts,1500).unref?.();
setInterval(purgeExpiredPulsePosts,5*60*1000).unref?.();

const HOSTINGER_PULSE_PROXY='https://quantic-pulse-api.onrender.com';
function shouldProxyPulse(req){
  const host=String(req.headers.host||'').toLowerCase();
  return host.includes('hostingersite.com')&&!usePostgres&&!useRemoteStore&&!useMysql;
}
async function proxyPulseRequest(req,res){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try{
    const method=String(req.method||'GET').toUpperCase();
    let body;
    if(!['GET','HEAD'].includes(method)){
      const chunks=[];let size=0;
      for await(const chunk of req){
        size+=chunk.length;
        if(size>1024*1024)throw Object.assign(new Error('body_too_large'),{status:413});
        chunks.push(chunk);
      }
      body=chunks.length?Buffer.concat(chunks):undefined;
    }
    const target=new URL(req.originalUrl||req.url,HOSTINGER_PULSE_PROXY);
    const response=await fetch(target,{
      method,
      redirect:'error',
      cache:'no-store',
      signal:controller.signal,
      headers:{
        accept:String(req.headers.accept||'application/json'),
        ...(req.headers.authorization?{authorization:String(req.headers.authorization)}:{}),
        ...(req.headers['content-type']?{'content-type':String(req.headers['content-type'])}:{})
      },
      body
    });
    const payload=Buffer.from(await response.arrayBuffer());
    const headers={
      'content-type':response.headers.get('content-type')||'application/json; charset=utf-8',
      'cache-control':'no-store',
      'x-quantic-pulse-backend':'quantic-relay'
    };
    res.writeHead(response.status,headers);
    res.end(payload);
  }catch(error){
    console.error('[pulse] durable proxy failed',String(error?.message||error));
    if(!res.headersSent)json(res,error?.status||503,{error:'pulse_storage_unavailable'});
    else if(!res.writableEnded)res.end();
  }finally{clearTimeout(timer)}
}

export function installQuanticPulse(app){
  if(app.__quanticPulseInstalled)return;
  app.__quanticPulseInstalled=true;
  const configuredOrigins=String(process.env.PULSE_CORS_ORIGINS||'https://mediumorchid-badger-314305.hostingersite.com')
    .split(',').map(value=>value.trim()).filter(Boolean);
  const allowedOrigins=new Set(configuredOrigins);
  app.use('/api/pulse',async(req,res,next)=>{
    try{
      if(shouldProxyPulse(req)){await proxyPulseRequest(req,res);return}
      const origin=String(req.headers.origin||'');
      const corsHeaders={};
      if(origin&&allowedOrigins.has(origin)){
        corsHeaders['access-control-allow-origin']=origin;
        corsHeaders['access-control-allow-methods']='GET,POST,PATCH,OPTIONS';
        corsHeaders['access-control-allow-headers']='Content-Type, Authorization';
        corsHeaders['access-control-max-age']='600';
        corsHeaders['vary']='Origin';
      }
      if(req.method==='OPTIONS'){
        if(origin&&!allowedOrigins.has(origin)){res.writeHead(403,{'cache-control':'no-store'});res.end();return}
        res.writeHead(204,corsHeaders);res.end();return;
      }
      const url=new URL(req.originalUrl||req.url,'http://localhost');
      const handled=await handlePulse(req,res,url,corsHeaders);
      if(!handled&&!res.headersSent)next();
    }catch(error){
      next(error);
    }
  });
}
