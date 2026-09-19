import test from "node:test";
import assert from "node:assert/strict";
import {generateIdentity,encryptPortable,decryptPortable,signAssertion,verifyAssertion} from "../src/vault-core.mjs";

test("portable vault encrypts and decrypts an Ed25519 private key",()=>{
  const identity=generateIdentity("USB");
  const encrypted=encryptPortable(identity.privateKeyPem,"12345678-local");
  assert.notEqual(encrypted.ciphertext,identity.privateKeyPem);
  assert.equal(decryptPortable(encrypted,"12345678-local"),identity.privateKeyPem);
});

test("identity signs a challenge verifiable with its public key",()=>{
  const identity=generateIdentity("PC");
  const assertion=signAssertion(identity.privateKeyPem,{keyId:identity.keyId,challenge:"0123456789abcdef",audience:"quantic-mail"});
  assert.equal(verifyAssertion(identity.publicKey,assertion.payload,assertion.signature),true);
});
