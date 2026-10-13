import assert from 'node:assert/strict';
import {readFileSync,existsSync,readdirSync} from 'node:fs';
const source=readFileSync('scripts/sync-quantic-mail.mjs','utf8');
assert.ok(source.includes('verifyDevicePairingBundle(work)'),'verified QR client required for sync');
assert.ok(source.includes('DIST_COMMIT="6721988f546458d0c307f39a1334039e39f8d3a3"'),'current QuanticMail static distribution');
assert.ok(source.includes('SOURCE_COMMIT="9aa0d89b3e008eee909b850bc5a1775b75ddcbfe"'),'matching source manifest');
const folder='public/mail/_next/static/chunks/app/devices';
if(existsSync(folder)){
 const files=readdirSync(folder).filter(f=>/^page-[\w-]+\.js$/.test(f));
 assert.equal(files.length,1,'one device QR entry point');
 const compiled=readFileSync(folder+'/'+files[0],'utf8');
 assert.ok(!compiled.includes('toString("base64url")'),'unsupported Buffer encoder absent');
 assert.ok(!compiled.includes(',"base64url")'),'unsupported Buffer decoder absent');
 assert.ok(compiled.includes('btoa(Array.from('),'browser-safe encoder present');
 assert.ok(compiled.includes('Uint8Array.from(atob('),'browser-safe decoder present');
 const html=readFileSync('public/mail/devices/index.html','utf8');
 assert.ok(html.includes(files[0]),'device HTML references real compiled bundle');
 assert.ok(html.includes('quantic-mail-id-gate.js'),'Quantic ID access guard remains');
}
console.log(JSON.stringify({ok:true,contract:'mail-recovered-onboarding-native-qr',checked:existsSync(folder)}));
