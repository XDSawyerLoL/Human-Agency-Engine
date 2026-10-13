import fs from 'node:fs';
import {createHash,generateKeyPairSync,sign} from 'node:crypto';

const base=process.env.BASE_URL||'http://127.0.0.1:3000';
const cookieFile=process.env.COOKIE_FILE||'/tmp/quantic-id-cookie.txt';

function b64url(value){return Buffer.from(value).toString('base64url')}

const deniedApi=await fetch(base+'/api/snapshot',{redirect:'manual'});
if(deniedApi.status!==401)throw new Error('expected /api/snapshot 401 without Quantic ID, got '+deniedApi.status);

const deniedPage=await fetch(base+'/vision/',{redirect:'manual'});
if(deniedPage.status!==302)throw new Error('expected /vision/ 302 without Quantic ID, got '+deniedPage.status);
const location=deniedPage.headers.get('location')||'';
if(!location.startsWith('/quantic/?next='))throw new Error('Vision did not redirect to Quantic ID');

// Mail's static entry must load before its own browser-side Quantic ID gate
// can check Identity Vault. No mailbox contents are exposed by this HTML route.
const publicMailShell=await fetch(base+'/mail/',{redirect:'manual'});
if(publicMailShell.status!==200)throw new Error('expected /mail/ static shell 200, got '+publicMailShell.status);
const publicMailHtml=await publicMailShell.text();
if(!publicMailHtml.includes('quantic-mail-id-gate.js'))throw new Error('Mail client-side Vault gate missing');
if(!publicMailHtml.includes('Retrouvez votre boîte Mail'))throw new Error('Mail recovery UI not served');
const publicMailDevices=await fetch(base+'/mail/devices/',{redirect:'manual'});
if(publicMailDevices.status!==200)throw new Error('Mail device QR route unavailable: '+publicMailDevices.status);

const challengeResponse=await fetch(base+'/api/id/challenge',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});
if(!challengeResponse.ok)throw new Error('challenge failed');
const challenge=await challengeResponse.json();

const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const publicDer=publicKey.export({type:'spki',format:'der'});
const publicKeyB64=b64url(publicDer);
const keyId='qid_'+createHash('sha256').update(publicDer).digest('hex').slice(0,32);
const payload=JSON.stringify({
  version:1,
  keyId,
  challenge:challenge.challenge,
  audience:challenge.audience,
  issuedAt:new Date().toISOString()
});
const signature=b64url(sign(null,Buffer.from(payload),privateKey));
const proof={version:1,keyId,publicKey:publicKeyB64,payload,signature};

const sessionResponse=await fetch(base+'/api/id/session',{
  method:'POST',
  headers:{'content-type':'application/json'},
  body:JSON.stringify({proof}),
  redirect:'manual'
});
if(!sessionResponse.ok)throw new Error('session failed: '+sessionResponse.status+' '+await sessionResponse.text());
const session=await sessionResponse.json();
if(!session.authenticated||session.keyId!==keyId)throw new Error('invalid authenticated session response');
const setCookie=sessionResponse.headers.get('set-cookie')||'';
const cookie=setCookie.split(';')[0];
if(!cookie.startsWith('quantic_id_session='))throw new Error('missing Quantic ID session cookie');
fs.writeFileSync(cookieFile,cookie,'utf8');

const privatePage=await fetch(base+'/vision/',{headers:{cookie},redirect:'manual'});
if(!privatePage.ok)throw new Error('authenticated Vision page failed: '+privatePage.status);
const html=await privatePage.text();
if(!html.includes('qv8-hero'))throw new Error('native Vision V8 home not served');

const privateMail=await fetch(base+'/mail/',{headers:{cookie},redirect:'manual'});
if(!privateMail.ok)throw new Error('authenticated Mail page failed: '+privateMail.status);
const mailHtml=await privateMail.text();
if(!mailHtml.includes('QuanticMail'))throw new Error('native Quantic Mail page not served');

console.log(JSON.stringify({ok:true,keyId,cookieFile,redirect:location}));
