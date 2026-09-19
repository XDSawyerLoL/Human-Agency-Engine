import test from "node:test";
import assert from "node:assert/strict";
import {generateIdentity,encryptPortable,decryptPortable,normalizeIdentityProfile,signAssertion,verifyAssertion} from "../src/vault-core.mjs";

test("portable vault encrypts and decrypts an Ed25519 private key",()=>{
  const identity=generateIdentity("USB");
  const encrypted=encryptPortable(identity.privateKeyPem,"12345678-local");
  assert.notEqual(encrypted.ciphertext,identity.privateKeyPem);
  assert.equal(decryptPortable(encrypted,"12345678-local"),identity.privateKeyPem);
});

test("portable vault can encrypt a complete private identity profile",()=>{
  const identity=generateIdentity("USB profile");
  const profile=normalizeIdentityProfile({
    firstName:"Ada",
    lastName:"Lovelace",
    email:"ada@example.test",
    city:"London",
    photoDataUrl:"data:image/png;base64,aGVsbG8="
  });
  const payload=JSON.stringify({version:2,privateKeyPem:identity.privateKeyPem,profile});
  const encrypted=encryptPortable(payload,"12345678-local");
  const decrypted=JSON.parse(decryptPortable(encrypted,"12345678-local"));
  assert.equal(decrypted.profile.firstName,"Ada");
  assert.equal(decrypted.profile.lastName,"Lovelace");
  assert.equal(decrypted.profile.email,"ada@example.test");
  assert.equal(decrypted.profile.photoDataUrl,"data:image/png;base64,aGVsbG8=");
  assert.equal(decrypted.privateKeyPem,identity.privateKeyPem);
});

test("identity profile rejects non-image data URLs",()=>{
  assert.throws(()=>normalizeIdentityProfile({photoDataUrl:"data:text/plain;base64,aGVsbG8="}),/profile_photo_invalid/);
});

test("identity signs a challenge verifiable with its public key",()=>{
  const identity=generateIdentity("PC");
  const assertion=signAssertion(identity.privateKeyPem,{keyId:identity.keyId,challenge:"0123456789abcdef",audience:"quantic-mail"});
  assert.equal(verifyAssertion(identity.publicKey,assertion.payload,assertion.signature),true);
});
