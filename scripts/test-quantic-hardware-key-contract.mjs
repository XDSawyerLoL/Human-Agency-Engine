import assert from "node:assert/strict";
import fs from "node:fs";
import {createHash,generateKeyPairSync,sign} from "node:crypto";
import {verifyIdentityProof} from "../src/quantic_identity.js";

function b64url(value){return Buffer.from(value).toString("base64url");}
function qid(publicDer){return "qid_"+createHash("sha256").update(publicDer).digest("hex").slice(0,32);}

const challenge="qhk-test-challenge-0123456789";
const audience="quantic-sillage";

{
  const {publicKey,privateKey}=generateKeyPairSync("ec",{namedCurve:"prime256v1"});
  const publicDer=publicKey.export({type:"spki",format:"der"});
  const keyId=qid(publicDer);
  const payload=JSON.stringify({version:1,keyId,challenge,audience,issuedAt:new Date().toISOString()});
  const signature=b64url(sign("sha256",Buffer.from(payload),{key:privateKey,dsaEncoding:"ieee-p1363"}));
  const proof={version:1,algorithm:"ecdsa-p256-sha256",keyId,publicKey:b64url(publicDer),payload,signature};
  const verified=verifyIdentityProof(proof,challenge);
  assert.equal(verified.error,undefined);
  assert.equal(verified.keyId,keyId);
  assert.equal(verified.algorithm,"ecdsa-p256-sha256");
}

{
  const {publicKey,privateKey}=generateKeyPairSync("ed25519");
  const publicDer=publicKey.export({type:"spki",format:"der"});
  const keyId=qid(publicDer);
  const payload=JSON.stringify({version:1,keyId,challenge,audience,issuedAt:new Date().toISOString()});
  const signature=b64url(sign(null,Buffer.from(payload),privateKey));
  const verified=verifyIdentityProof({version:1,algorithm:"ed25519",keyId,publicKey:b64url(publicDer),payload,signature},challenge);
  assert.equal(verified.error,undefined);
  assert.equal(verified.algorithm,"ed25519");
}

const main=fs.readFileSync("identity-vault/src/main.mjs","utf8");
const host=fs.readFileSync("identity-vault/src/hardware-key.js","utf8");
const protocol=fs.readFileSync("hardware-key/PROTOCOL.md","utf8");
const pulse=fs.readFileSync("src/quantic_pulse.js","utf8");

for(const marker of [
  "quantic-hardware-key",
  "ecdsa-p256-sha256",
  "privateKeyExportable:false",
  "hardware:sign-request"
]) assert.ok(main.includes(marker),marker);

for(const marker of ["navigator.hid","0xcafe","0x5148","PROVISION","SIGN"])assert.ok(host.includes(marker),marker);
assert.ok(protocol.includes("ne doit jamais être exportée"));
assert.ok(protocol.includes("Une implémentation purement logicielle"));
assert.ok(pulse.includes("ecdsa-p256-sha256"));

for(const forbidden of ["Microsoft Platform Crypto Provider","New-SelfSignedCertificate","Cert:\\CurrentUser"]){
  assert.equal(main.includes(forbidden),false,forbidden);
  assert.equal(host.includes(forbidden),false,forbidden);
}

console.log(JSON.stringify({ok:true,contract:"quantic-hardware-key-qhk1"}));
