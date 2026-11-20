import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {generateUsbUnlockToken,generateIdentity} from '../src/vault-core.mjs';
import {USB_PASSPHRASE_MODE,encryptUsbPassphrase,decryptUsbPassphrase} from '../src/usb-two-factor.mjs';

const phrase='des fleurs rares tombent sur la neige en hiver';
test('USB 2FA requires both a secret on the drive and an independent memorized phrase',()=>{
 const usb=generateUsbUnlockToken(),identity=generateIdentity('Test USB 2FA');
 const ciphertext=encryptUsbPassphrase(identity.privateKeyPem,usb,phrase);
 assert.equal(USB_PASSPHRASE_MODE,'usb-passphrase');
 assert.equal(ciphertext.kdf,'scrypt-usb-passphrase-v1');
 assert.equal(ciphertext.N,131072);
 assert.equal(ciphertext.r,8);
 assert.equal(ciphertext.p,1);
 assert.ok(!JSON.stringify(ciphertext).includes(identity.privateKeyPem));
 assert.ok(!JSON.stringify(ciphertext).includes(phrase));
 assert.ok(!JSON.stringify(ciphertext).includes(usb));
 assert.equal(decryptUsbPassphrase(ciphertext,usb,phrase),identity.privateKeyPem);
 assert.throws(()=>decryptUsbPassphrase(ciphertext,usb,'mauvaise phrase avec assez de longueur'),/usb_passphrase_invalid/);
 assert.throws(()=>decryptUsbPassphrase(ciphertext,generateUsbUnlockToken(),phrase),/usb_passphrase_invalid/);
});
test('weak or absent phrases cannot create a copyable USB identity',()=>{
 const usb=generateUsbUnlockToken();
 assert.throws(()=>encryptUsbPassphrase('secret',usb,''),/usb_passphrase_required/);
 assert.throws(()=>encryptUsbPassphrase('secret',usb,'1234567890123456'),/usb_passphrase_required|usb_passphrase_weak/);
 assert.throws(()=>encryptUsbPassphrase('secret','not_a_32_byte_usb_token',phrase),/usb_key_invalid/);
});
test('USB cipher metadata cannot force attacker-chosen scrypt parameters',()=>{
 const usb=generateUsbUnlockToken();
 const c=encryptUsbPassphrase('secret',usb,phrase);
 for(const variant of [{...c,N:1},{...c,N:2**24},{...c,r:1},{...c,cipher:'aes-128-gcm'}]){
  assert.throws(()=>decryptUsbPassphrase(variant,usb,phrase),/usb_vault_format_invalid/);
 }
});
test('portable identity creation, legacy signing and upgrade obey security invariant',()=>{
 const main=readFileSync(new URL('../src/main.mjs',import.meta.url),'utf8');
 const preload=readFileSync(new URL('../src/preload.cjs',import.meta.url),'utf8');
 const renderer=readFileSync(new URL('../src/renderer.js',import.meta.url),'utf8');
 const html=readFileSync(new URL('../src/index.html',import.meta.url),'utf8');
 assert.match(main,/unlockMode:USB_PASSPHRASE_MODE/);
 assert.match(main,/usb_existing_identity_requires_migration/);
 assert.match(main,/function migrateLegacyUsb/);
 assert.match(main,/usb_upgrade_required/);
 assert.match(main,/if\(loadRecord\(\)\?\.unlockMode==="usb-presence"\)/);
 assert.match(main,/renameSync\(tmp,path\)/);
 assert.match(preload,/migrateUsb:/);
 assert.match(renderer,/IdentityVault\.migrateUsb\(/);
 assert.match(html,/id="unlock-passphrase"/);
 assert.match(html,/id="upgrade-form"/);
 assert.match(html,/id="profile-passphrase"/);
});
