import assert from 'node:assert/strict';
import {randomBytes,createHash} from 'node:crypto';
import {encodeBase64Url,decodeBase64Url} from '../src/quantic_base64url.js';
for(const size of [1,2,3,16,32,64,128,512]){
  const bytes=randomBytes(size);
  const encoded=encodeBase64Url(bytes);
  assert.match(encoded,/^[A-Za-z0-9_-]+$/);
  assert.deepEqual(decodeBase64Url(encoded),bytes);
  assert.equal(createHash('sha256').update(decodeBase64Url(encoded)).digest('hex'),createHash('sha256').update(bytes).digest('hex'));
}
for(const invalid of ['','a','%','AA=','AA+','AA/','abc?','AQ_','_','Zg==',123,null]){
 assert.throws(()=>decodeBase64Url(invalid),/invalid_base64url/);
}
console.log(JSON.stringify({ok:true,contract:'quantic-base64url-node-compat'}));
