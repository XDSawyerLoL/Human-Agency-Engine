import test from "node:test";
import assert from "node:assert/strict";
import {generateIdentity,generateUsbUnlockToken,encryptPortable,decryptPortable,decryptPortableRecord,normalizeIdentityProfile,signAssertion,verifyAssertion} from "../src/vault-core.mjs";

test("USB presence token is machine-generated and strong",()=>{
  const token=generateUsbUnlockToken();
  assert.ok(token.length>=43);
  assert.notEqual(token,generateUsbUnlockToken());
});

test("USB presence token encrypts and decrypts an Ed25519 private key",()=>{
  const identity=generateIdentity("USB");
  const token=generateUsbUnlockToken();
  const encrypted=encryptPortable(identity.privateKeyPem,token);
  assert.notEqual(encrypted.ciphertext,identity.privateKeyPem);
  assert.equal(decryptPortable(encrypted,token),identity.privateKeyPem);
});

test("legacy v1 USB record remains cryptographically readable when its old code is known",()=>{
  const identity=generateIdentity("Legacy USB");
  const record={
    version:1,
    mode:"portable",
    keyId:identity.keyId,
    publicKey:identity.publicKey,
    encryptedPrivateKey:encryptPortable(identity.privateKeyPem,"12345678-local")
  };
  assert.equal(decryptPortableRecord(record,"12345678-local"),identity.privateKeyPem);
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
  const payload=JSON.stringify({version:3,privateKeyPem:identity.privateKeyPem,profile});
  const token=generateUsbUnlockToken();
  const encrypted=encryptPortable(payload,token);
  const decrypted=JSON.parse(decryptPortable(encrypted,token));
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
