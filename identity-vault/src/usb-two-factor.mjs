'use strict';
// Two independent factors: USB-held random token + passphrase never written to
// that USB. A copied drive without the memorized phrase cannot decrypt offline
// except by guessing it. This is NOT equivalent to non-exportable hardware.
import {createCipheriv,createDecipheriv,createHmac,randomBytes,scryptSync} from 'node:crypto';

const N=1<<17,R=8,P=1,MAXMEM=256*1024*1024;
export const USB_PASSPHRASE_MODE='usb-passphrase';
const KDF='scrypt-usb-passphrase-v1';
function requireToken(token){
 const value=String(token||'');
 if(!/^[A-Za-z0-9_-]{43}$/.test(value) || Buffer.from(value,'base64url').length!==32)
  throw Error('usb_key_invalid');
 return value;
}
function requirePhrase(phrase){
 if(typeof phrase!=='string'||phrase.length<16||phrase.length>256||phrase.trim().length<16)
  throw Error('usb_passphrase_required');
 if(/^(.{1,4})\1{3,}$/.test(phrase))throw Error('usb_passphrase_weak');
 return phrase;
}
function keyFor(phrase,token,salt){
 const key=scryptSync(requirePhrase(phrase),salt,32,{N,r:R,p:P,maxmem:MAXMEM});
 try{
  return createHmac('sha256',key).update('QIV-USB-PASSPHRASE-v1\0').update(requireToken(token)).digest();
 }finally{key.fill(0)}
}
function b64(data){return Buffer.from(data).toString('base64url')}
function decoded(value,length){
 if(typeof value!=='string'||!new RegExp('^[A-Za-z0-9_-]{'+Math.ceil(length*4/3-2)+','+Math.ceil(length*4/3+2)+'}$').test(value))
  throw Error('usb_vault_format_invalid');
 const raw=Buffer.from(value,'base64url');
 if(raw.length!==length)throw Error('usb_vault_format_invalid');
 return raw;
}
export function encryptUsbPassphrase(plaintext,token,phrase){
 requireToken(token);requirePhrase(phrase);
 const salt=randomBytes(16),iv=randomBytes(12),key=keyFor(phrase,token,salt);
 try{
  const cipher=createCipheriv('aes-256-gcm',key,iv);
  const ciphertext=Buffer.concat([cipher.update(String(plaintext),'utf8'),cipher.final()]);
  return {kdf:KDF,cipher:'aes-256-gcm',N,r:R,p:P,salt:b64(salt),iv:b64(iv),tag:b64(cipher.getAuthTag()),ciphertext:b64(ciphertext)};
 }finally{key.fill(0)}
}
export function decryptUsbPassphrase(encrypted,token,phrase){
 if(encrypted?.kdf!==KDF||encrypted?.cipher!=='aes-256-gcm'||encrypted?.N!==N||encrypted?.r!==R||encrypted?.p!==P)
  throw Error('usb_vault_format_invalid');
 const salt=decoded(encrypted.salt,16),iv=decoded(encrypted.iv,12),tag=decoded(encrypted.tag,16);
 if(typeof encrypted.ciphertext!=='string'||encrypted.ciphertext.length>16_000_000||!(/^[A-Za-z0-9_-]*$/.test(encrypted.ciphertext)))
  throw Error('usb_vault_format_invalid');
 const key=keyFor(phrase,token,salt);
 try{
  const decipher=createDecipheriv('aes-256-gcm',key,iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(Buffer.from(encrypted.ciphertext,'base64url')),decipher.final()]).toString('utf8');
 }catch{throw Error('usb_passphrase_invalid')}
 finally{key.fill(0)}
}
