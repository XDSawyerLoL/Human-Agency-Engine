import {
  createCipheriv,
  createDecipheriv,
  createHash,
  createPrivateKey,
  createPublicKey,
  generateKeyPairSync,
  randomBytes,
  scryptSync,
  sign,
  verify
} from "node:crypto";

function b64url(buffer){return Buffer.from(buffer).toString("base64url");}
function requirePassphrase(passphrase){
  const value=String(passphrase||"");
  if(value.length<8)throw new Error("portable_passphrase_too_short");
  return value;
}

export function generateIdentity(label="Mon identité Quantic"){
  const {publicKey,privateKey}=generateKeyPairSync("ed25519");
  const publicDer=publicKey.export({type:"spki",format:"der"});
  const privatePem=privateKey.export({type:"pkcs8",format:"pem"}).toString();
  const keyId="qid_"+createHash("sha256").update(publicDer).digest("hex").slice(0,32);
  return {keyId,label:String(label||"Quantic ID").trim().slice(0,80)||"Quantic ID",publicKey:b64url(publicDer),privateKeyPem:privatePem};
}

export function encryptPortable(privateKeyPem,passphrase){
  const secret=requirePassphrase(passphrase);
  const salt=randomBytes(16),iv=randomBytes(12);
  const key=scryptSync(secret,salt,32);
  const cipher=createCipheriv("aes-256-gcm",key,iv);
  const ciphertext=Buffer.concat([cipher.update(String(privateKeyPem),"utf8"),cipher.final()]);
  return {kdf:"scrypt",cipher:"aes-256-gcm",salt:b64url(salt),iv:b64url(iv),tag:b64url(cipher.getAuthTag()),ciphertext:b64url(ciphertext)};
}

export function decryptPortable(record,passphrase){
  const secret=requirePassphrase(passphrase);
  if(record?.kdf!=="scrypt"||record?.cipher!=="aes-256-gcm")throw new Error("portable_vault_format_invalid");
  const key=scryptSync(secret,Buffer.from(record.salt,"base64url"),32);
  const decipher=createDecipheriv("aes-256-gcm",key,Buffer.from(record.iv,"base64url"));
  decipher.setAuthTag(Buffer.from(record.tag,"base64url"));
  return Buffer.concat([decipher.update(Buffer.from(record.ciphertext,"base64url")),decipher.final()]).toString("utf8");
}

export function assertionPayload({keyId,challenge,audience="",issuedAt=new Date().toISOString()}){
  const c=String(challenge||"");
  if(c.length<16||c.length>4096)throw new Error("invalid_challenge");
  return JSON.stringify({version:1,keyId:String(keyId),challenge:c,audience:String(audience||"").slice(0,300),issuedAt});
}

export function signAssertion(privateKeyPem,input){
  const payload=assertionPayload(input);
  const signature=sign(null,Buffer.from(payload),createPrivateKey(privateKeyPem));
  return {payload,signature:b64url(signature)};
}

export function verifyAssertion(publicKeyB64url,payload,signature){
  const publicKey=createPublicKey({key:Buffer.from(publicKeyB64url,"base64url"),type:"spki",format:"der"});
  return verify(null,Buffer.from(payload),publicKey,Buffer.from(signature,"base64url"));
}
