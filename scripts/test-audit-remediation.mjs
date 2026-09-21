import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import express from 'express';
import { EvidenceStore } from '../src/store.js';
import { buildCalibrationReport } from '../src/calibration_engine.js';

function b64url(value){return Buffer.from(value).toString('base64url');}
function sha(value){return createHash('sha256').update(String(value)).digest('hex');}
function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms));}

async function testPulsePrivacy(){
  const dir=await mkdtemp(join(tmpdir(),'quantic-pulse-audit-'));
  try{
    await mkdir(dir,{recursive:true});
    const token='audit-user-b-token';
    const store={
      version:1,
      users:{
        u_a:{id:'u_a',handle:'alpha',displayName:'Alpha',bio:'',avatar:'',verified:false,createdAt:new Date().toISOString()},
        u_b:{id:'u_b',handle:'bravo',displayName:'Bravo',bio:'',avatar:'',verified:false,createdAt:new Date().toISOString()}
      },
      handles:{alpha:'u_a',bravo:'u_b'},
      sessions:{[sha(token)]:{userId:'u_b',createdAt:Date.now(),expiresAt:Date.now()+60_000,presenceUntil:Date.now()+60_000}},
      posts:{
        p_private:{id:'p_private',authorId:'u_a',body:'PRIVATE-AUDIT-SECRET',createdAt:new Date().toISOString(),replyToId:null,quotePostId:null,circleId:'c_private',linkUrl:'',linkTitle:'',imageUrl:'',mediaUrl:'',mediaType:'',deletedAt:null},
        p_public_quote:{id:'p_public_quote',authorId:'u_b',body:'Public wrapper',createdAt:new Date().toISOString(),replyToId:null,quotePostId:'p_private',circleId:null,linkUrl:'',linkTitle:'',imageUrl:'',mediaUrl:'',mediaType:'',deletedAt:null},
        p_expired:{id:'p_expired',authorId:'u_b',body:'expired-public-post',createdAt:new Date(Date.now()-25*60*60*1000).toISOString(),replyToId:null,quotePostId:null,circleId:null,linkUrl:'',linkTitle:'',imageUrl:'',mediaUrl:'',mediaType:'',deletedAt:null},
        p_recent:{id:'p_recent',authorId:'u_b',body:'recent-public-post',createdAt:new Date(Date.now()-60*60*1000).toISOString(),replyToId:null,quotePostId:null,circleId:null,linkUrl:'',linkTitle:'',imageUrl:'',mediaUrl:'',mediaType:'',deletedAt:null}
      },
      follows:{u_a:[],u_b:[]},likes:{},reposts:{},bookmarks:{u_a:[],u_b:[]},
      circles:{c_private:{id:'c_private',ownerId:'u_a',name:'Private',description:'',visibility:'private',createdAt:new Date().toISOString()}},
      circleMembers:{c_private:{u_a:'owner'}},notifications:{},reports:{},blocks:{u_a:[],u_b:[]},
      secureDevices:{
        u_a:{dev_a:{deviceId:'dev_a',encryptionPublicKey:b64url(Buffer.alloc(32,1)),signingPublicKey:b64url(Buffer.alloc(32,2)),identityKeyId:'qid_a',registeredAt:new Date().toISOString(),protocol:'pulse-e2ee-v1'}},
        u_b:{dev_b:{deviceId:'dev_b',encryptionPublicKey:b64url(Buffer.alloc(32,3)),signingPublicKey:b64url(Buffer.alloc(32,4)),identityKeyId:'qid_b',registeredAt:new Date().toISOString(),protocol:'pulse-e2ee-v1'}}
      },
      conversations:{'u_a:u_b':{members:['u_a','u_b'],messageIds:['m_old','m_recent'],createdAt:new Date(Date.now()-26*60*60*1000).toISOString()}},
      messages:{
        m_old:{id:'m_old',conversationKey:'u_a:u_b',senderId:'u_a',recipientId:'u_b',body:'old-persistent-message',createdAt:new Date(Date.now()-25*60*60*1000).toISOString(),expiresAt:new Date(Date.now()-60*60*1000).toISOString(),readAt:null},
        m_recent:{id:'m_recent',conversationKey:'u_a:u_b',senderId:'u_a',recipientId:'u_b',body:'recent-message',createdAt:new Date(Date.now()-60*60*1000).toISOString(),readAt:null}
      }
    };
    await writeFile(join(dir,'pulse.json'),JSON.stringify(store),'utf8');
    process.env.DATA_DIR=dir;
    const {handlePulse}=await import('../src/quantic_pulse.js?audit='+Date.now());

    function request(method,path,{authToken='',body}={}){
      const chunks=body===undefined?[]:[Buffer.from(JSON.stringify(body))];
      const req=Readable.from(chunks);
      req.method=method;
      req.url=path;
      req.originalUrl=path;
      req.headers={};
      if(authToken)req.headers.authorization='Bearer '+authToken;
      req.headers['x-forwarded-for']='127.0.0.1';
      req.socket={remoteAddress:'127.0.0.1'};
      return req;
    }
    async function call(method,path,options={}){
      const req=request(method,path,options);
      let status=0,raw='';
      const res={
        headersSent:false,writableEnded:false,
        writeHead(code){status=code;this.headersSent=true;},
        end(value=''){raw+=String(value);this.writableEnded=true;}
      };
      await handlePulse(req,res,new URL('http://audit.local'+path),{});
      return {status,body:raw?JSON.parse(raw):null};
    }

    const direct=await call('GET','/api/pulse/posts/p_private',{authToken:token});
    assert.equal(direct.status,404,'non-member direct read must be denied');

    const bookmark=await call('POST','/api/pulse/posts/p_private/bookmark',{authToken:token});
    assert.equal(bookmark.status,404,'secondary actions must not disclose private posts');

    const quoteCreate=await call('POST','/api/pulse/posts',{authToken:token,body:{body:'Attempted leak',quotePostId:'p_private'}});
    assert.equal(quoteCreate.status,404,'a non-member must not quote a private post');

    const publicFeed=await call('GET','/api/pulse/feed?mode=discover');
    assert.equal(publicFeed.status,200);
    const wrapper=publicFeed.body.posts.find(post=>post.id==='p_public_quote');
    assert.ok(wrapper,'public wrapper should still render');
    assert.equal(wrapper.quote,null,'nested serialization must filter an inaccessible quoted post');
    assert.doesNotMatch(JSON.stringify(publicFeed.body),/PRIVATE-AUDIT-SECRET/,'private body must never escape through a public quote');

    assert.equal(publicFeed.body.posts.some(post=>post.id==='p_expired'),false,'public posts older than 24 hours must disappear');
    assert.equal(publicFeed.body.posts.some(post=>post.id==='p_recent'),true,'public posts younger than 24 hours must remain');


    const messages=await call('GET','/api/pulse/messages/alpha',{authToken:token});
    assert.equal(messages.status,200);
    assert.equal(messages.body.messageMode,'persistent','private messages must be persistent');
    assert.deepEqual(messages.body.messages.map(message=>message.id),['m_old','m_recent'],'private messages must not inherit the 24-hour post expiry');
    assert.equal('expiresAt' in messages.body.messages[0],false,'legacy message expiry metadata must not control private-message retention');

    const health=await call('GET','/api/pulse/health');
    assert.equal(health.status,200);
    assert.equal(health.body.postRetentionHours,24,'Pulse health must publish the 24-hour public-post retention contract');
    assert.equal(health.body.privateMessages,'persistent','Pulse health must distinguish persistent private messages from ephemeral posts');
    assert.equal(health.body.sessions,'pulse-session-v2','Pulse must advertise the active session-v2 protocol');
    assert.equal(health.body.ratchet,'dh-double-ratchet-v1','Pulse must advertise its DH Double Ratchet contract');
    assert.equal(health.body.prekeys,'pulse-prekey-v2','Pulse must advertise hybrid-capable signed prekeys');
    assert.equal(health.body.writeDurability,'ack-after-durable-commit','Pulse must never acknowledge an ephemeral-only write');

    const plaintextSend=await call('POST','/api/pulse/messages',{authToken:token,body:{handle:'alpha',body:'server must never store me'}});
    assert.equal(plaintextSend.status,400);
    assert.equal(plaintextSend.body.error,'e2ee_required','new private messages must fail closed when not encrypted');

    const ciphertext=b64url(Buffer.alloc(32,9));
    const encryptedSend=await call('POST','/api/pulse/messages',{authToken:token,body:{
      handle:'alpha',
      protocol:'pulse-e2ee-v1',
      clientMessageId:'audit-secure-message',
      senderDeviceId:'dev_b',
      sentAt:new Date().toISOString(),
      envelopes:[{
        recipientDeviceId:'dev_a',
        ephemeralPublicKey:b64url(Buffer.alloc(32,5)),
        salt:b64url(Buffer.alloc(32,6)),
        iv:b64url(Buffer.alloc(12,7)),
        ciphertext,
        signature:b64url(Buffer.alloc(64,8))
      }]
    }});
    assert.equal(encryptedSend.status,201,'opaque encrypted envelope should be accepted');
    const persisted=JSON.parse(await (await import('node:fs/promises')).readFile(join(dir,'pulse.json'),'utf8'));
    const secureMessage=Object.values(persisted.messages).find(message=>message.clientMessageId==='audit-secure-message');
    assert.ok(secureMessage,'encrypted message must persist');
    assert.equal(secureMessage.protocol,'pulse-e2ee-v1');
    assert.equal('body' in secureMessage,false,'server must not persist private-message plaintext');
    assert.equal(secureMessage.envelopes[0].ciphertext,ciphertext);

    const sessionCiphertext=b64url(Buffer.alloc(48,11));
    const sessionSend=await call('POST','/api/pulse/messages',{authToken:token,body:{
      handle:'alpha',
      protocol:'pulse-session-v2',
      clientMessageId:'audit-session-v2-message',
      senderDeviceId:'dev_b',
      sentAt:new Date().toISOString(),
      envelopes:[{
        protocol:'pulse-session-v2',
        recipientDeviceId:'dev_a',
        header:{
          sessionId:'00000000-0000-4000-8000-000000000002',
          dh:b64url(Buffer.alloc(32,12)),
          pn:0,
          n:0,
          handshake:{
            protocol:'pulse-handshake-v2',
            preKeyId:'0123456789abcdef0123456789abcdef',
            ephemeralPublicKey:b64url(Buffer.alloc(32,13)),
            profile:'classical-v2',
            pqAlgorithm:'',
            pqCiphertext:''
          }
        },
        iv:b64url(Buffer.alloc(12,14)),
        ciphertext:sessionCiphertext,
        signature:b64url(Buffer.alloc(64,15))
      }]
    }});
    assert.equal(sessionSend.status,201,'Pulse session-v2 opaque envelope should be accepted');
    const persistedV2=JSON.parse(await (await import('node:fs/promises')).readFile(join(dir,'pulse.json'),'utf8'));
    const sessionMessage=Object.values(persistedV2.messages).find(message=>message.clientMessageId==='audit-session-v2-message');
    assert.ok(sessionMessage,'session-v2 message must persist');
    assert.equal(sessionMessage.protocol,'pulse-session-v2');
    assert.equal('body' in sessionMessage,false,'session-v2 server record must not contain plaintext');
    assert.equal(sessionMessage.envelopes[0].header.n,0);
    assert.equal(sessionMessage.envelopes[0].ciphertext,sessionCiphertext);

    const logout=await call('POST','/api/pulse/auth/logout',{authToken:token,body:{}});
    assert.equal(logout.status,200,'locking/leaving Pulse must be able to revoke the session');
    const anonymousFeedAfterLogout=await call('GET','/api/pulse/feed?mode=discover');
    assert.equal(anonymousFeedAfterLogout.status,200);
    assert.equal(
      anonymousFeedAfterLogout.body.posts.some(post=>post.id==='p_recent'),
      true,
      'revoking the identity/session must never delete a public post before its 24-hour expiry'
    );
  }finally{
    delete process.env.DATA_DIR;
    await rm(dir,{recursive:true,force:true});
  }
}

async function testContinuousIdentityPresence(){
  process.env.QUANTIC_ID_PRESENCE_LEASE_MS='300';
  const {installQuanticIdentity,requireQuanticIdentity}=await import('../src/quantic_identity.js?audit='+Date.now());
  const app=express();
  app.use(express.json({limit:'64kb'}));
  installQuanticIdentity(app);
  app.use(requireQuanticIdentity);
  app.get('/api/private-audit',(_req,res)=>res.json({ok:true}));
  const server=await new Promise((resolve,reject)=>{
    const instance=app.listen(0,'127.0.0.1',()=>resolve(instance));
    instance.once('error',reject);
  });
  try{
    const address=server.address();
    const base='http://127.0.0.1:'+address.port;
    const {publicKey,privateKey}=generateKeyPairSync('ed25519');
    const publicDer=publicKey.export({type:'spki',format:'der'});
    const publicKeyB64=b64url(publicDer);
    const keyId='qid_'+createHash('sha256').update(publicDer).digest('hex').slice(0,32);

    async function signChallenge(challenge){
      const payload=JSON.stringify({version:1,keyId,challenge:challenge.challenge,audience:challenge.audience,issuedAt:new Date().toISOString()});
      return {version:1,keyId,publicKey:publicKeyB64,payload,signature:b64url(sign(null,Buffer.from(payload),privateKey))};
    }

    const challenge=await (await fetch(base+'/api/id/challenge',{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).json();
    const sessionResponse=await fetch(base+'/api/id/session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({proof:await signChallenge(challenge)})});
    assert.equal(sessionResponse.status,200);
    const cookie=(sessionResponse.headers.get('set-cookie')||'').split(';')[0];
    assert.match(cookie,/^quantic_id_session=/);

    assert.equal((await fetch(base+'/api/private-audit',{headers:{cookie}})).status,200,'fresh presence must authorize protected API');
    await sleep(420);
    assert.equal((await fetch(base+'/api/private-audit',{headers:{cookie}})).status,401,'expired presence lease must revoke protected API before the 12h session expires');

    const presenceChallengeResponse=await fetch(base+'/api/id/presence/challenge',{method:'POST',headers:{cookie,'content-type':'application/json'},body:'{}'});
    assert.equal(presenceChallengeResponse.status,200,'expired presence must still be renewable by the same session and Vault key');
    const presenceChallenge=await presenceChallengeResponse.json();
    const renew=await fetch(base+'/api/id/presence',{method:'POST',headers:{cookie,'content-type':'application/json'},body:JSON.stringify({proof:await signChallenge(presenceChallenge)})});
    assert.equal(renew.status,200);
    assert.equal((await fetch(base+'/api/private-audit',{headers:{cookie}})).status,200,'valid Vault proof must restore the short presence lease');
  }finally{
    await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
    delete process.env.QUANTIC_ID_PRESENCE_LEASE_MS;
  }
}

async function testImmutableForecastDeadline(){
  const store=new EvidenceStore();
  const first='2028-08-31T00:00:00.000Z';
  const moved='2028-09-01T00:00:00.000Z';
  const base={scenario_key:'audit-scenario',scenario_id:'audit',title:'Audit scenario',domain:'audit',horizon_tier:'long',status:'active',probability:{estimate:.4,percent:40,interval_percent:[20,60]}};
  await store.recordForecastRegistry([{...base,target_date:first}],new Date('2026-09-01T00:00:00Z').toISOString());
  await store.recordForecastRegistry([{...base,target_date:moved,probability:{...base.probability,estimate:.5,percent:50}}],new Date('2026-09-02T00:00:00Z').toISOString());
  assert.equal(store.registry.get('audit-scenario').target_at,first,'same scenario key must keep its first published deadline');
}

function testCalibrationQualityGate(){
  const bad=Array.from({length:30},(_,i)=>({scenario_key:'bad-'+i,outcome:0,first_probability:.99,domain:'audit',horizon_tier:'near',resolution_kind:'binary_event'}));
  const badReport=buildCalibrationReport(bad);
  assert.equal(badReport.calibration_sample_ready,true);
  assert.equal(badReport.calibration_quality_ready,false);
  assert.equal(badReport.calibration_ready,false,'30 catastrophically wrong forecasts must never be called calibrated');

  const good=Array.from({length:30},(_,i)=>({scenario_key:'good-'+i,outcome:1,first_probability:.9,domain:'audit',horizon_tier:'near',resolution_kind:'binary_event'}));
  const goodReport=buildCalibrationReport(good);
  assert.equal(goodReport.calibration_sample_ready,true);
  assert.equal(goodReport.calibration_quality_ready,true);
  assert.equal(goodReport.calibration_ready,true);
}

await testPulsePrivacy();
await testContinuousIdentityPresence();
await testImmutableForecastDeadline();
testCalibrationQualityGate();

console.log(JSON.stringify({ok:true,audit_remediation:['A01','A02','A05','A06']}));
