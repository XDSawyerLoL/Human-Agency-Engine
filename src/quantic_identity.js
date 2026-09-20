import {createHash,createPublicKey,randomBytes,verify} from 'node:crypto';

const COOKIE='quantic_id_session';
const AUDIENCE='quantic-sillage';
const CHALLENGE_TTL=120000;
const SESSION_TTL=12*60*60*1000;
const PRESENCE_LEASE_MS=Math.max(250,Number(process.env.QUANTIC_ID_PRESENCE_LEASE_MS||12000));
const challenges=new Map();
const sessions=new Map();
const INTERNAL_HEADER='x-quantic-internal';
const INTERNAL_TOKEN=randomBytes(32).toString('hex');

const privatePagePrefixes=[
  '/vision','/mail','/predictions','/analyst','/alerts','/sports','/cameras',
  '/track-record','/sources','/backtest','/settings','/causal','/crypto',
  '/horizons','/intelligence','/matches','/modules'
];

function now(){return Date.now()}
function clean(v,max=4096){return String(v??'').trim().slice(0,max)}
function hash(v){return createHash('sha256').update(String(v)).digest('hex')}
function keyId(publicKey){return 'qid_'+createHash('sha256').update(Buffer.from(publicKey,'base64url')).digest('hex').slice(0,32)}
function parseCookies(req){
  const out={};
  for(const part of String(req.headers.cookie||'').split(';')){
    const i=part.indexOf('=');
    if(i<1)continue;
    out[decodeURIComponent(part.slice(0,i).trim())]=decodeURIComponent(part.slice(i+1).trim());
  }
  return out;
}
function cleanup(){
  const t=now();
  for(const [k,v] of challenges)if(v.expiresAt<=t)challenges.delete(k);
  for(const [k,v] of sessions)if(v.expiresAt<=t)sessions.delete(k);
}
function secureRequest(req){
  return req.secure||String(req.headers['x-forwarded-proto']||'').split(',')[0].trim()==='https';
}
function setSessionCookie(req,res,token){
  const parts=[
    COOKIE+'='+encodeURIComponent(token),
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    'Max-Age='+Math.floor(SESSION_TTL/1000)
  ];
  if(secureRequest(req))parts.push('Secure');
  res.setHeader('Set-Cookie',parts.join('; '));
}
function clearSessionCookie(req,res){
  const parts=[COOKIE+'=','Path=/','HttpOnly','SameSite=Lax','Max-Age=0'];
  if(secureRequest(req))parts.push('Secure');
  res.setHeader('Set-Cookie',parts.join('; '));
}
function publicSession(session){
  return session?{authenticated:true,keyId:session.keyId,algorithm:session.algorithm||"ed25519",expiresAt:new Date(session.expiresAt).toISOString(),presenceUntil:new Date(session.presenceUntil).toISOString(),presenceLeaseMs:PRESENCE_LEASE_MS}:{authenticated:false};
}
function sessionFromRequest(req,{requirePresence=true}={}){
  cleanup();
  const token=parseCookies(req)[COOKIE];
  if(!token)return null;
  const session=sessions.get(hash(token));
  if(!session||session.expiresAt<=now())return null;
  if(requirePresence&&(!session.presenceUntil||session.presenceUntil<=now()))return null;
  return session;
}
export function verifyIdentityProof(proof,expectedChallenge){
  if(!proof||typeof proof!=='object')return{error:'identity_proof_required'};
  const publicKey=clean(proof.publicKey,1600),proofKeyId=clean(proof.keyId,90),payload=String(proof.payload||''),signature=clean(proof.signature,1400);
  const algorithm=clean(proof.algorithm||'ed25519',80);
  if(!publicKey||!proofKeyId||!payload||!signature)return{error:'identity_proof_required'};
  let parsed;
  try{parsed=JSON.parse(payload)}catch{return{error:'identity_proof_invalid'}}
  if(parsed.challenge!==expectedChallenge||parsed.audience!==AUDIENCE||parsed.keyId!==proofKeyId)return{error:'identity_proof_invalid'};
  if(keyId(publicKey)!==proofKeyId)return{error:'identity_proof_invalid'};
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
  return{keyId:proofKeyId,publicKey,algorithm};
}
function issueChallenge(meta={}){
  cleanup();
  const challenge=randomBytes(32).toString('base64url');
  challenges.set(challenge,{expiresAt:now()+CHALLENGE_TTL,...meta});
  return{challenge,audience:AUDIENCE,expiresAt:new Date(now()+CHALLENGE_TTL).toISOString()};
}
function establishSession(req,res,proof){
  cleanup();
  let parsed;
  try{parsed=JSON.parse(String(proof?.payload||''))}catch{return{error:'identity_proof_invalid'}}
  const challenge=clean(parsed?.challenge,4096);
  const record=challenges.get(challenge);
  if(!record||record.expiresAt<=now())return{error:'identity_challenge_expired'};
  if(record.purpose&&record.purpose!=='session')return{error:'identity_challenge_mismatch'};
  challenges.delete(challenge);
  const verified=verifyIdentityProof(proof,challenge);
  if(verified.error)return verified;
  const token=randomBytes(32).toString('base64url');
  const session={keyId:verified.keyId,publicKey:verified.publicKey,algorithm:verified.algorithm||"ed25519",createdAt:now(),expiresAt:now()+SESSION_TTL,presenceUntil:now()+PRESENCE_LEASE_MS};
  sessions.set(hash(token),session);
  setSessionCookie(req,res,token);
  return publicSession(session);
}

export function installQuanticIdentity(app){
  app.post('/api/id/challenge',(_req,res)=>{
    res.set('Cache-Control','no-store');
    res.json(issueChallenge({purpose:'session'}));
  });
  app.post('/api/id/session',(req,res)=>{
    res.set('Cache-Control','no-store');
    const result=establishSession(req,res,req.body?.proof);
    if(result.error)return res.status(401).json(result);
    res.json(result);
  });
  app.get('/api/id/session',(req,res)=>{
    res.set('Cache-Control','no-store');
    res.json(publicSession(sessionFromRequest(req)));
  });
  app.post('/api/id/presence/challenge',(req,res)=>{
    res.set('Cache-Control','no-store');
    const session=sessionFromRequest(req,{requirePresence:false});
    if(!session)return res.status(401).json({error:'quantic_id_required'});
    res.json(issueChallenge({purpose:'presence',keyId:session.keyId}));
  });
  app.post('/api/id/presence',(req,res)=>{
    res.set('Cache-Control','no-store');
    const session=sessionFromRequest(req,{requirePresence:false});
    if(!session)return res.status(401).json({error:'quantic_id_required'});
    let parsed;
    try{parsed=JSON.parse(String(req.body?.proof?.payload||''));}catch{return res.status(401).json({error:'identity_proof_invalid'});}
    const challenge=clean(parsed?.challenge,4096),record=challenges.get(challenge);
    if(!record||record.expiresAt<=now())return res.status(401).json({error:'identity_challenge_expired'});
    if(record.purpose!=='presence'||record.keyId!==session.keyId)return res.status(401).json({error:'identity_challenge_mismatch'});
    challenges.delete(challenge);
    const verified=verifyIdentityProof(req.body?.proof,challenge);
    if(verified.error)return res.status(401).json(verified);
    if(verified.keyId!==session.keyId||verified.publicKey!==session.publicKey)return res.status(401).json({error:'identity_mismatch'});
    session.presenceUntil=now()+PRESENCE_LEASE_MS;
    res.json(publicSession(session));
  });
  app.post('/api/id/logout',(req,res)=>{
    const token=parseCookies(req)[COOKIE];
    if(token)sessions.delete(hash(token));
    clearSessionCookie(req,res);
    res.set('Cache-Control','no-store');
    res.json({ok:true});
  });
}

function isPrivatePage(pathname){
  return privatePagePrefixes.some(prefix=>pathname===prefix||pathname===prefix+'/'||pathname.startsWith(prefix+'/'));
}
function isPublicApi(pathname){
  return pathname==='/api/health'||pathname.startsWith('/api/id/')||pathname.startsWith('/api/pulse/')||pathname.startsWith('/api/quantic-portal/');
}
export function quanticInternalHeaders(){
  return {[INTERNAL_HEADER]:INTERNAL_TOKEN};
}
function internalRequest(req){
  return req.get(INTERNAL_HEADER)===INTERNAL_TOKEN;
}
export function requireQuanticIdentity(req,res,next){
  const pathname=req.path||'/';
  if(internalRequest(req))return next();
  const privatePage=isPrivatePage(pathname);
  const privateApi=pathname.startsWith('/api/')&&!isPublicApi(pathname);
  if(!privatePage&&!privateApi)return next();
  const session=sessionFromRequest(req);
  if(session){req.quanticIdentity=session;return next();}
  if(privateApi){
    res.set('Cache-Control','no-store');
    return res.status(401).json({error:'quantic_id_required'});
  }
  const nextPath=pathname+(req.originalUrl.includes('?')?'?'+req.originalUrl.split('?').slice(1).join('?'):'');
  return res.redirect(302,'/quantic/?next='+encodeURIComponent(nextPath));
}
