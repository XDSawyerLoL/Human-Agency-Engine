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
function clean(value,max=240){
  return String(value||"").trim().slice(0,max);
}

export function normalizeIdentityProfile(profile={}){
  const source=profile&&typeof profile==="object"?profile:{};
  const photoDataUrl=String(source.photoDataUrl||"").trim();
  if(photoDataUrl){
    if(!/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(photoDataUrl))throw new Error("profile_photo_invalid");
    if(photoDataUrl.length>3_000_000)throw new Error("profile_photo_too_large");
  }
  return {
    firstName:clean(source.firstName,100),
    middleNames:clean(source.middleNames,160),
    lastName:clean(source.lastName,100),
    preferredName:clean(source.preferredName,100),
    birthDate:clean(source.birthDate,32),
    birthPlace:clean(source.birthPlace,160),
    nationality:clean(source.nationality,120),
    gender:clean(source.gender,80),
    email:clean(source.email,200),
    phone:clean(source.phone,80),
    addressLine1:clean(source.addressLine1,200),
    addressLine2:clean(source.addressLine2,200),
    postalCode:clean(source.postalCode,32),
    city:clean(source.city,120),
    region:clean(source.region,120),
    country:clean(source.country,120),
    occupation:clean(source.occupation,160),
    organization:clean(source.organization,180),
    website:clean(source.website,300),
    emergencyContactName:clean(source.emergencyContactName,160),
    emergencyContactPhone:clean(source.emergencyContactPhone,80),
    notes:clean(source.notes,2000),
    photoDataUrl
  };
}

export function generateIdentity(label="Mon identité Quantic"){
  const {publicKey,privateKey}=generateKeyPairSync("ed25519");
  const publicDer=publicKey.export({type:"spki",format:"der"});
  const privatePem=privateKey.export({type:"pkcs8",format:"pem"}).toString();
  const keyId="qid_"+createHash("sha256").update(publicDer).digest("hex").slice(0,32);
  return {keyId,label:String(label||"Quantic ID").trim().slice(0,80)||"Quantic ID",publicKey:b64url(publicDer),privateKeyPem:privatePem};
}

export function generateUsbUnlockToken(){
  return randomBytes(32).toString("base64url");
}

export function encryptPortable(secretValue,passphrase){
  const secret=requirePassphrase(passphrase);
  const salt=randomBytes(16),iv=randomBytes(12);
  const key=scryptSync(secret,salt,32);
  const cipher=createCipheriv("aes-256-gcm",key,iv);
  const ciphertext=Buffer.concat([cipher.update(String(secretValue),"utf8"),cipher.final()]);
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

export function decryptPortableRecord(record,passphrase){
  const encrypted=record?.encryptedSecret||record?.encryptedPrivateKey;
  if(!encrypted)throw new Error("portable_vault_format_invalid");
  return decryptPortable(encrypted,passphrase);
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
