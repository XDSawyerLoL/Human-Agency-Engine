import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
const sync=readFileSync('scripts/sync-quantic-mail.mjs','utf8');
assert.ok(sync.includes('patchDevicePairingBundle(work)'),'paired client correction must run during Hostinger sync');
assert.ok(sync.includes('h.from(e).toString("base64url")'),'legacy encoder contract');
assert.ok(sync.includes('h.from(e,"base64url")'),'legacy decoder contract');
assert.ok(sync.includes('qrfix20261013.js'),'cache-busted bundle name');
assert.ok(sync.includes('RELAY_SOURCE_COMMIT="3b5ae4ff4fc084801f56b5bed2713f0a424ca15c"'),'upstream QuanticMail device fix pinned');
const file='public/mail/_next/static/chunks/app/devices/page-088a8b8f4a087ea5-qrfix20261013.js';
if(existsSync(file)){
 const compiled=readFileSync(file,'utf8');
 assert.ok(!compiled.includes('toString("base64url")'),'old broken QR encoder');
 assert.ok(!compiled.includes('h.from(e,"base64url")'),'old broken QR decoder');
 assert.ok(compiled.includes('toString("base64").replace('));
 assert.ok(compiled.includes('h.from(e.replace('));
 const html=readFileSync('public/mail/devices/index.html','utf8');
 assert.ok(html.includes('page-088a8b8f4a087ea5-qrfix20261013.js'),'device HTML must reference newly named patched bundle');
}
console.log(JSON.stringify({ok:true,contract:'hostinger-mail-device-qr-buffer-compat',bundleChecked:existsSync(file)}));
