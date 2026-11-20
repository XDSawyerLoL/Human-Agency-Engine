import {app,BrowserWindow,dialog,ipcMain,powerMonitor,safeStorage,shell} from "electron";
import {createServer} from "node:http";
import {createHash,createPublicKey,randomBytes} from "node:crypto";
import {copyFileSync,existsSync,mkdirSync,readFileSync,renameSync,unlinkSync,writeFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
import {generateIdentity,generateUsbUnlockToken,encryptPortable,decryptPortableRecord,normalizeIdentityProfile,assertionPayload,signAssertion} from "./vault-core.mjs";
import {USB_PASSPHRASE_MODE,encryptUsbPassphrase,decryptUsbPassphrase} from "./usb-two-factor.mjs";

const __dirname=dirname(fileURLToPath(import.meta.url));
const HOST="127.0.0.1";
const PORT=47621;
const USB_KEY_FILENAME="identity-vault.key";
const HARDWARE_ALGORITHM="ecdsa-p256-sha256";
const HARDWARE_UNLOCK_MODE="quantic-hardware-key";
const HARDWARE_VENDOR_ID=0xcafe;
const HARDWARE_PRODUCT_ID=0x5148;
const isPortable=Boolean(process.env.PORTABLE_EXECUTABLE_DIR);
const allowedOrigins=new Set([
  "https://mediumorchid-badger-314305.hostingersite.com",
  "https://xdsawyerlol.github.io",
  "https://swapp.tv",
  "https://www.swapp.tv"
]);

let vaultPath="";
let activeIdentity=null;
let bridge=null;
let bridgeError="";
let presenceTimer=null;
let hardwarePermissionConfigured=false;
const pendingHardwareSigns=new Map();
const approvedWebOrigins=new Set();
const VAULT_IDLE_LOCK_SECONDS=15*60;
function siteApprovalKey(origin){return String(activeIdentity?.keyId||"")+"|"+origin;}
function isInternalMailOrigin(origin){return origin==="http://127.0.0.1:18787"||origin==="http://localhost:18787";}
function mayRevealPublicIdentity(origin){
 return isInternalMailOrigin(origin)||(Boolean(activeIdentity)&&approvedWebOrigins.has(siteApprovalKey(origin)));
}
function approveQuanticSiteOrigin(origin,audience){
 if(!origin||!localOriginAllowed(origin))throw new Error("site_origin_not_allowed");
 // Local Quantic Mail must request explicit user approval too. Previously its
 // local Origin + fixed audience bypassed the confirmation entirely.
 const internalMail=isInternalMailOrigin(origin)&&audience==="quantic-mail-desktop";
 if(!internalMail&&audience!==origin)throw new Error("quantic_audience_must_match_site");
 if(!activeIdentity)throw new Error("identity_locked");
 const key=siteApprovalKey(origin);
 if(approvedWebOrigins.has(key))return;
 const options={
   type:"question",title:"Quantic ID · autorisation de site",
   message:"Autoriser ce site à vérifier votre identité Quantic ID ?",
   detail:origin+"\n\nLe site recevra votre clé publique et une preuve signée pour cette session, jamais votre clé privée. Le verrouillage révoque l’autorisation.",
   buttons:["Refuser","Autoriser pour cette session"],defaultId:0,cancelId:0,noLink:true
 };
 const owner=BrowserWindow.getFocusedWindow()||BrowserWindow.getAllWindows()[0];
 const answer=owner?dialog.showMessageBoxSync(owner,options):dialog.showMessageBoxSync(options);
 if(answer!==1)throw new Error("quantic_site_authorization_denied");
 approvedWebOrigins.add(key);
}

function localOriginAllowed(origin){
  if(!origin)return true;
  if(allowedOrigins.has(origin))return true;
  return /^http:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?$/.test(origin);
}

function corsHeaders(origin){
  if(!localOriginAllowed(origin))return null;
  const headers={
    "Access-Control-Allow-Methods":"GET,POST,OPTIONS",
    "Access-Control-Allow-Headers":"Content-Type",
    "Access-Control-Allow-Private-Network":"true",
    "Cache-Control":"no-store",
    "Content-Type":"application/json; charset=utf-8",
    "Vary":"Origin"
  };
  if(origin)headers["Access-Control-Allow-Origin"]=origin;
  return headers;
}

function json(res,status,payload,headers={}){
  res.writeHead(status,{...headers,"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"});
  res.end(JSON.stringify(payload));
}

async function readJsonBody(req,limit=32768){
  const chunks=[];let size=0;
  for await(const chunk of req){
    size+=chunk.length;
    if(size>limit)throw new Error("body_too_large");
    chunks.push(chunk);
  }
  if(!chunks.length)return{};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function vaultDirectory(){
  if(isPortable)return join(process.env.PORTABLE_EXECUTABLE_DIR,"QuanticIdentityVault");
  return app.getPath("userData");
}
function defaultVaultPath(){
  const dir=vaultDirectory();
  mkdirSync(dir,{recursive:true});
  return join(dir,"identity-vault.json");
}
function ensureVaultPath(){
  if(!vaultPath)vaultPath=defaultVaultPath();
  return vaultPath;
}
function keyPathFor(path=ensureVaultPath()){
  return join(dirname(path),USB_KEY_FILENAME);
}

function validateP256PublicKey(publicKeyB64url,keyId){
  const der=Buffer.from(String(publicKeyB64url||""),"base64url");
  if(!der.length)throw new Error("hardware_public_key_invalid");
  const key=createPublicKey({key:der,type:"spki",format:"der"});
  if(key.asymmetricKeyType!=="ec"||key.asymmetricKeyDetails?.namedCurve!=="prime256v1"){
    throw new Error("hardware_public_key_invalid");
  }
  const expected="qid_"+createHash("sha256").update(der).digest("hex").slice(0,32);
  if(expected!==String(keyId||""))throw new Error("hardware_key_id_invalid");
  return expected;
}

function validateRecord(record){
  if(!record||typeof record!=="object")throw new Error("vault_format_invalid");
  if(!["portable","pc"].includes(record.mode))throw new Error("vault_format_invalid");
  if(!record.keyId||!record.publicKey)throw new Error("vault_format_invalid");
  if(!record.encryptedSecret&&!record.encryptedPrivateKey)throw new Error("vault_format_invalid");
  if(record.unlockMode===HARDWARE_UNLOCK_MODE){
    validateP256PublicKey(record.publicKey,record.keyId);
    if(record.algorithm!==HARDWARE_ALGORITHM||!record.hardware?.deviceId)throw new Error("vault_format_invalid");
  }
  return record;
}
function readRecordAt(path){
  const record=JSON.parse(readFileSync(path,"utf8"));
  return validateRecord(record);
}
function loadRecord(){
  ensureVaultPath();
  if(!existsSync(vaultPath))return null;
  try{return readRecordAt(vaultPath)}catch{return null}
}
function saveRecord(record){
  const path=ensureVaultPath();
  mkdirSync(dirname(path),{recursive:true});
  // Write and rename in the same directory to avoid truncating a valid key on crash.
  const tmp=path+".tmp-"+randomBytes(8).toString("hex");
  try{
    writeFileSync(tmp,JSON.stringify(record,null,2),{encoding:"utf8",mode:0o600,flag:"wx"});
    renameSync(tmp,path);
  }finally{if(existsSync(tmp))try{unlinkSync(tmp)}catch{}}
}

function readUsbUnlockToken(record=loadRecord()){
  if(record?.mode!=="portable"||record?.unlockMode!=="usb-presence")throw new Error("usb_presence_not_supported");
  const path=keyPathFor();
  if(!existsSync(path))throw new Error("usb_key_missing");
  const token=String(readFileSync(path,"utf8")||"").trim();
  if(token.length<32)throw new Error("usb_key_invalid");
  return token;
}
function usbPresenceAvailable(record=loadRecord()){
  if(record?.mode!=="portable"||!["usb-presence",USB_PASSPHRASE_MODE].includes(record?.unlockMode))return false;
  try{return readUsbUnlockToken(record).length>=32}catch{return false}
}
function backupExistingPortableVault(target=ensureVaultPath()){
  if(!existsSync(target))return null;
  const stamp=new Date().toISOString().replace(/[:.]/g,"-");
  const backup=join(dirname(target),`identity-vault.backup-${stamp}.json`);
  copyFileSync(target,backup);
  const oldKey=join(dirname(target),USB_KEY_FILENAME);
  if(existsSync(oldKey)){
    copyFileSync(oldKey,join(dirname(target),`identity-vault.backup-${stamp}.key`));
  }
  return backup;
}

function secretPayload(privateKeyPem,profile){
  return JSON.stringify({
    version:5,
    privateKeyPem:String(privateKeyPem||""),
    profile:normalizeIdentityProfile(profile)
  });
}
function parseSecret(value){
  const raw=String(value||"");
  try{
    const parsed=JSON.parse(raw);
    if(parsed&&typeof parsed==="object"&&("profile" in parsed||"privateKeyPem" in parsed)){
      return {privateKeyPem:String(parsed.privateKeyPem||""),profile:normalizeIdentityProfile(parsed.profile||{})};
    }
  }catch{}
  return {privateKeyPem:raw,profile:normalizeIdentityProfile({})};
}

function publicStatus(){
  const record=loadRecord();
  if(activeIdentity&&!record)activeIdentity=null;
  if(activeIdentity&&record?.mode==="portable"&&["usb-presence",USB_PASSPHRASE_MODE].includes(record?.unlockMode)&&!usbPresenceAvailable(record)){
    activeIdentity=null;
    approvedWebOrigins.clear();
  }
  const hardwareMode=record?.unlockMode===HARDWARE_UNLOCK_MODE;
  const legacyVault=Boolean(record?.mode==="portable"&&!["usb-presence",USB_PASSPHRASE_MODE,HARDWARE_UNLOCK_MODE].includes(record?.unlockMode));
  const needsUsbUpgrade=Boolean(record?.mode==="portable"&&record?.unlockMode==="usb-presence");
  return {
    product:"Quantic Identity Vault",
    version:5,
    appVersion:app.getVersion(),
    bridge:{host:HOST,port:PORT,ready:Boolean(bridge),error:bridgeError||null},
    vaultMode:record?.mode||(isPortable?"portable":"pc"),
    unlockMode:record?.unlockMode||(record?.mode==="portable"?"legacy-code":"system"),
    keyAlgorithm:activeIdentity?.algorithm||record?.algorithm||"ed25519",
    hardwareMode,
    hardwareDeviceId:hardwareMode?record?.hardware?.deviceId||null:null,
    hardwareProtocol:hardwareMode?Number(record?.hardware?.protocol||1):null,
    keyAlgorithmLabel:hardwareMode?"P-256 · clé privée matérielle":"Ed25519",
    portableCipher:"aes-256-gcm",
    vaultExists:Boolean(record),
    vaultLoaded:Boolean(record),
    identityAvailable:Boolean(activeIdentity),
    usbPresenceAvailable:usbPresenceAvailable(record),
    legacyVault,
    needsUsbUpgrade,
    usbTwoFactorEnabled:record?.unlockMode===USB_PASSPHRASE_MODE,
    keyId:activeIdentity?.keyId||record?.keyId||null,
    label:activeIdentity?.label||record?.label||null,
    publicKey:activeIdentity?.publicKey||record?.publicKey||null,
    profile:activeIdentity?.profile||null,
    profileAvailable:Boolean(activeIdentity?.profile),
    formatVersion:Number(record?.version||1),
    vaultPath:ensureVaultPath()
  };
}

function createIdentity({label="",profile={},usbPassphrase=""}={}){
  const normalizedProfile=normalizeIdentityProfile(profile);
  const suggestedLabel=normalizedProfile.preferredName||[normalizedProfile.firstName,normalizedProfile.lastName].filter(Boolean).join(" ");
  const identity=generateIdentity(label||suggestedLabel||"Mon identité Quantic");
  const createdAt=new Date().toISOString();
  const secret=secretPayload(identity.privateKeyPem,normalizedProfile);

  if(isPortable){
    const target=ensureVaultPath();
    // Never overwrite a registered identity or preserve a copyable old
    // private key in an automatic backup. Use the in-place upgrade instead.
    if(existsSync(target))throw Error("usb_existing_identity_requires_migration");
    const token=generateUsbUnlockToken();
    const encryptedSecret=encryptUsbPassphrase(secret,token,usbPassphrase);
    // Store the random USB factor only on the USB; NEVER store the passphrase.
    writeFileSync(keyPathFor(target),token,{encoding:"utf8",mode:0o600,flag:"wx"});
    try{
      saveRecord({
        version:6,mode:"portable",unlockMode:USB_PASSPHRASE_MODE,
        algorithm:"ed25519",keyId:identity.keyId,label:identity.label,
        publicKey:identity.publicKey,encryptedSecret,createdAt
      });
    }catch(error){
      try{unlinkSync(keyPathFor(target))}catch{}
      throw error;
    }
    activeIdentity={...identity,algorithm:"ed25519",profile:normalizedProfile};
  }else{
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    const encryptedSecret=safeStorage.encryptString(secret).toString("base64");
    saveRecord({version:5,mode:"pc",unlockMode:"system",algorithm:"ed25519",keyId:identity.keyId,label:identity.label,publicKey:identity.publicKey,encryptedSecret,createdAt});
    activeIdentity={...identity,algorithm:"ed25519",profile:normalizedProfile};
  }
  return publicStatus();
}

function createHardwareIdentity({label="",profile={},deviceId="",publicKey="",keyId="",vaultKey=""}={}){
  if(!isPortable)throw new Error("hardware_portable_required");
  const cleanDeviceId=String(deviceId||"").trim().slice(0,160);
  const secretKey=String(vaultKey||"").trim();
  if(!cleanDeviceId)throw new Error("hardware_device_invalid");
  if(secretKey.length<32)throw new Error("hardware_vault_key_invalid");
  validateP256PublicKey(publicKey,keyId);
  const normalizedProfile=normalizeIdentityProfile(profile);
  const suggestedLabel=normalizedProfile.preferredName||[normalizedProfile.firstName,normalizedProfile.lastName].filter(Boolean).join(" ");
  const identityLabel=String(label||suggestedLabel||"Mon identité Quantic Hardware").trim().slice(0,80)||"Mon identité Quantic Hardware";
  const target=ensureVaultPath();
  if(loadRecord()?.unlockMode==="usb-presence")throw Error("usb_upgrade_required");
  backupExistingPortableVault(target);
  const encryptedSecret=encryptPortable(secretPayload("",normalizedProfile),secretKey);
  saveRecord({
    version:5,
    mode:"portable",
    unlockMode:HARDWARE_UNLOCK_MODE,
    algorithm:HARDWARE_ALGORITHM,
    keyId:String(keyId),
    label:identityLabel,
    publicKey:String(publicKey),
    encryptedSecret,
    hardware:{deviceId:cleanDeviceId,protocol:1,privateKeyExportable:false},
    createdAt:new Date().toISOString()
  });
  const softwareKey=keyPathFor(target);
  if(existsSync(softwareKey)){try{unlinkSync(softwareKey)}catch{}}
  activeIdentity={
    keyId:String(keyId),
    label:identityLabel,
    publicKey:String(publicKey),
    algorithm:HARDWARE_ALGORITHM,
    hardwareDeviceId:cleanDeviceId,
    profile:normalizedProfile
  };
  return publicStatus();
}

function unlockHardwareIdentity({deviceId="",vaultKey=""}={}){
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
  if(record.unlockMode!==HARDWARE_UNLOCK_MODE)throw new Error("hardware_mode_not_active");
  const cleanDeviceId=String(deviceId||"").trim();
  if(cleanDeviceId!==record.hardware?.deviceId)throw new Error("hardware_device_mismatch");
  const secretKey=String(vaultKey||"").trim();
  if(secretKey.length<32)throw new Error("hardware_vault_key_invalid");
  let secretValue="";
  try{secretValue=decryptPortableRecord(record,secretKey)}
  catch{throw new Error("hardware_vault_unlock_failed")}
  const secret=parseSecret(secretValue);
  activeIdentity={
    keyId:record.keyId,
    label:record.label,
    publicKey:record.publicKey,
    algorithm:HARDWARE_ALGORITHM,
    hardwareDeviceId:cleanDeviceId,
    profile:secret.profile
  };
  return publicStatus();
}

function unlockIdentity({usbPassphrase=""}={}){
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
  if(record.unlockMode===HARDWARE_UNLOCK_MODE)throw new Error("hardware_unlock_required");
  let secretValue="";
  if(record.mode==="portable"){
    if(![USB_PASSPHRASE_MODE,"usb-presence"].includes(record.unlockMode))throw Error("legacy_vault_requires_code");
    try{
      const token=readUsbUnlockToken({...record,unlockMode:"usb-presence"});
      secretValue=record.unlockMode===USB_PASSPHRASE_MODE
        ?decryptUsbPassphrase(record.encryptedSecret,token,usbPassphrase)
        :decryptPortableRecord(record,token);
    }catch(error){
      const code=String(error?.message||error);
      if(["usb_key_missing","usb_key_invalid","usb_passphrase_required","usb_passphrase_weak","usb_passphrase_invalid"].includes(code))throw error;
      throw Error("usb_vault_unlock_failed");
    }
  }else if(record.mode==="pc"){
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    try{
      secretValue=safeStorage.decryptString(Buffer.from(record.encryptedSecret||record.encryptedPrivateKey,"base64"));
    }catch{
      throw new Error("pc_unlock_failed");
    }
  }else{
    throw new Error("vault_format_invalid");
  }
  const secret=parseSecret(secretValue);
  activeIdentity={
    keyId:record.keyId,
    label:record.label,
    publicKey:record.publicKey,
    algorithm:record.algorithm||"ed25519",
    privateKeyPem:secret.privateKeyPem,
    profile:secret.profile
  };
  return publicStatus();
}

function migrateLegacyUsb({usbPassphrase=""}={}){
  const record=loadRecord();
  if(record?.mode!=="portable"||record.unlockMode!=="usb-presence")
    throw Error("usb_upgrade_not_required");
  if(!activeIdentity?.privateKeyPem||activeIdentity.keyId!==record.keyId)
    throw Error("identity_locked");
  const token=readUsbUnlockToken(record);
  // Preserve the same public identity: existing SWAPP associations still work.
  // Historical cloned backups remain a risk until this key is rotated.
  const encryptedSecret=encryptUsbPassphrase(
    secretPayload(activeIdentity.privateKeyPem,activeIdentity.profile),token,usbPassphrase);
  saveRecord({...record,version:6,unlockMode:USB_PASSPHRASE_MODE,
    encryptedSecret,updatedAt:new Date().toISOString()});
  approvedWebOrigins.clear();
  activeIdentity=null;
  return publicStatus();
}

function updateProfile(profile={},hardwareVaultKey="",usbPassphrase=""){
  if(!activeIdentity)throw new Error("identity_locked");
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
  const normalizedProfile=normalizeIdentityProfile(profile);
  const nextLabel=normalizedProfile.preferredName||[normalizedProfile.firstName,normalizedProfile.lastName].filter(Boolean).join(" ")||record.label||activeIdentity.label;
  const privateKeyPem=record.unlockMode===HARDWARE_UNLOCK_MODE?"":activeIdentity.privateKeyPem;
  const secret=secretPayload(privateKeyPem,normalizedProfile);
  let encryptedSecret;

  if(record.unlockMode===HARDWARE_UNLOCK_MODE){
    const key=String(hardwareVaultKey||"").trim();
    if(key.length<32)throw new Error("hardware_vault_key_required");
    encryptedSecret=encryptPortable(secret,key);
  }else if(record.mode==="portable"){
    if(record.unlockMode!==USB_PASSPHRASE_MODE)throw Error("usb_upgrade_required");
    const token=readUsbUnlockToken({...record,unlockMode:"usb-presence"});
    // Ensure the correct phrase is supplied before updating. Otherwise a
    // typo could irreversibly rewrite a valid identity with a new phrase.
    try{decryptUsbPassphrase(record.encryptedSecret,token,usbPassphrase)}
    catch{throw Error("usb_passphrase_invalid")}
    encryptedSecret=encryptUsbPassphrase(secret,token,usbPassphrase);
  }else{
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    encryptedSecret=safeStorage.encryptString(secret).toString("base64");
  }

  const next={
    ...record,
    version:5,
    label:nextLabel,
    encryptedSecret,
    updatedAt:new Date().toISOString()
  };
  saveRecord(next);
  activeIdentity={...activeIdentity,label:nextLabel,profile:normalizedProfile};
  return publicStatus();
}

async function loadVaultFile(){
  const owner=BrowserWindow.getFocusedWindow()||BrowserWindow.getAllWindows()[0];
  const options={
    title:"Charger un coffre Quantic Identity Vault",
    properties:["openFile"],
    filters:[
      {name:"Coffre Quantic Identity Vault",extensions:["json","qivault"]},
      {name:"Tous les fichiers",extensions:["*"]}
    ]
  };
  const result=owner?await dialog.showOpenDialog(owner,options):await dialog.showOpenDialog(options);
  if(result.canceled||!result.filePaths?.[0])return publicStatus();
  const selected=result.filePaths[0];
  readRecordAt(selected);
  vaultPath=selected;
  activeIdentity=null;
  approvedWebOrigins.clear();
  return publicStatus();
}

function lockIdentity(){
  activeIdentity=null;
  approvedWebOrigins.clear();
  // A Windows screen lock or suspend also invalidates outstanding hardware
  // signature requests; a late reply cannot reactivate the key.
  for(const pending of pendingHardwareSigns.values()){
    clearTimeout(pending.timer);
    pending.reject(new Error("identity_locked"));
  }
  pendingHardwareSigns.clear();
  return publicStatus();
}
function tryAutoUnlockInstalled(){
  if(isPortable)return;
  const record=loadRecord();
  if(record?.mode!=="pc")return;
  try{unlockIdentity()}catch{}
}
function startPresenceMonitor(){
  if(presenceTimer)clearInterval(presenceTimer);
  presenceTimer=setInterval(()=>{
    if(!activeIdentity)return;
    // Windows idle includes time without mouse/keyboard input, unlike SWAPP's
    // background polling. The Vault must not remain unlocked indefinitely.
    try{if(powerMonitor.getSystemIdleTime()>=VAULT_IDLE_LOCK_SECONDS){lockIdentity();return;}}catch{}
    const record=loadRecord();
    if(!record||(record.mode==="portable"&&["usb-presence",USB_PASSPHRASE_MODE].includes(record.unlockMode)&&!usbPresenceAvailable(record))){
      activeIdentity=null;
      approvedWebOrigins.clear();
    }
  },1000);
}

function requestHardwareSignature(payload,deviceId){
  const win=BrowserWindow.getAllWindows()[0];
  if(!win||win.isDestroyed())return Promise.reject(new Error("hardware_bridge_unavailable"));
  const id=createHash("sha256").update(String(Date.now())+Math.random()).digest("hex").slice(0,24);
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{
      pendingHardwareSigns.delete(id);
      reject(new Error("hardware_sign_timeout"));
    },12000);
    pendingHardwareSigns.set(id,{resolve,reject,timer,deviceId});
    win.webContents.send("hardware:sign-request",{id,payload,deviceId});
  });
}

function configureHardwarePermissions(win){
  if(hardwarePermissionConfigured)return;
  const ses=win.webContents.session;
  ses.setDevicePermissionHandler(details=>{
    const device=details.device;
    return details.deviceType==="hid"&&device?.vendorId===HARDWARE_VENDOR_ID&&device?.productId===HARDWARE_PRODUCT_ID;
  });
  ses.on("select-hid-device",(event,details,callback)=>{
    event.preventDefault();
    const device=details.deviceList.find(item=>item.vendorId===HARDWARE_VENDOR_ID&&item.productId===HARDWARE_PRODUCT_ID);
    callback(device?.deviceId||"");
  });
  hardwarePermissionConfigured=true;
}

function startBridge(){
  if(bridge)return;
  bridge=createServer(async(req,res)=>{
    const origin=String(req.headers.origin||"");
    const cors=corsHeaders(origin);
    if(!cors)return json(res,403,{error:"origin_not_allowed"});
    if(req.method==="OPTIONS"){
      res.writeHead(204,cors);res.end();return;
    }
    const url=new URL(req.url||"/","http://"+HOST+":"+PORT);
    if(url.pathname==="/v1/status"&&req.method==="GET"){
      const status=publicStatus();
      return json(res,200,{
        version:1,
        product:"Quantic Identity Vault",
        appVersion:status.appVersion,
        vaultFormatVersion:status.formatVersion,
        identityAvailable:status.identityAvailable,
        keyId:mayRevealPublicIdentity(origin)?status.keyId:null,
        label:mayRevealPublicIdentity(origin)?status.label:null,
        publicKey:mayRevealPublicIdentity(origin)?status.publicKey:null,
        algorithm:status.keyAlgorithm,
        hardwareMode:status.hardwareMode,
        vaultMode:status.vaultMode
      },cors);
    }
    if(url.pathname==="/v1/assert"&&req.method==="POST"){
      if(!activeIdentity)return json(res,423,{error:"identity_locked"},cors);
      // Old removable-storage keys are copyable. Require migration before signing.
      if(loadRecord()?.unlockMode==="usb-presence")return json(res,426,{error:"usb_upgrade_required"},cors);
      try{
        const body=await readJsonBody(req);
        const input={
          keyId:activeIdentity.keyId,
          challenge:body.challenge,
          audience:body.audience||origin||""
        };
        approveQuanticSiteOrigin(origin,input.audience);
        if(activeIdentity.algorithm===HARDWARE_ALGORITHM){
          const payload=assertionPayload(input);
          const keyId=activeIdentity.keyId;
          const signature=await requestHardwareSignature(payload,activeIdentity.hardwareDeviceId);
          if(activeIdentity?.keyId!==keyId||!mayRevealPublicIdentity(origin))return json(res,423,{error:"identity_locked"},cors);
          return json(res,200,{
            version:1,
            algorithm:HARDWARE_ALGORITHM,
            keyId:activeIdentity.keyId,
            publicKey:activeIdentity.publicKey,
            payload,
            signature
          },cors);
        }
        const assertion=signAssertion(activeIdentity.privateKeyPem,input);
        return json(res,200,{version:1,algorithm:"ed25519",keyId:activeIdentity.keyId,publicKey:activeIdentity.publicKey,...assertion},cors);
      }catch(error){
        return json(res,400,{error:String(error?.message||error)},cors);
      }
    }
    return json(res,404,{error:"not_found"},cors);
  });
  bridge.on("error",error=>{
    bridgeError=String(error?.message||error);
    bridge=null;
  });
  bridge.listen(PORT,HOST,()=>{bridgeError="";});
}

function createWindow(){
  const win=new BrowserWindow({
    width:980,
    height:860,
    minWidth:760,
    minHeight:640,
    backgroundColor:"#f5f7f9",
    title:`Quantic Identity Vault ${app.getVersion()}`,
    webPreferences:{
      preload:join(__dirname,"preload.cjs"),
      contextIsolation:true,
      nodeIntegration:false,
      sandbox:true
    }
  });
  configureHardwarePermissions(win);
  win.removeMenu();
  win.loadFile(join(__dirname,"index.html"));
}

ipcMain.handle("vault:status",()=>publicStatus());
ipcMain.handle("vault:create",(_event,options)=>createIdentity(options||{}));
ipcMain.handle("vault:create-hardware",(_event,options)=>createHardwareIdentity(options||{}));
ipcMain.handle("vault:load-file",()=>loadVaultFile());
ipcMain.handle("vault:unlock",(_event,options)=>unlockIdentity(options||{}));
ipcMain.handle("vault:migrate-usb",(_event,options)=>migrateLegacyUsb(options||{}));
ipcMain.handle("vault:unlock-hardware",(_event,options)=>unlockHardwareIdentity(options||{}));
ipcMain.handle("vault:update-profile",(_event,{profile,hardwareVaultKey,usbPassphrase}={})=>updateProfile(profile||{},hardwareVaultKey||"",usbPassphrase||""));
ipcMain.handle("vault:lock",()=>lockIdentity());
ipcMain.handle("vault:hardware-disconnected",(_event,{deviceId}={})=>{
  if(activeIdentity?.algorithm===HARDWARE_ALGORITHM&&(!deviceId||deviceId===activeIdentity.hardwareDeviceId)){
    activeIdentity=null;
    approvedWebOrigins.clear();
  }
  return publicStatus();
});
ipcMain.on("hardware:sign-response",(_event,response={})=>{
  const id=String(response.id||"");
  const pending=pendingHardwareSigns.get(id);
  if(!pending)return;
  pendingHardwareSigns.delete(id);
  clearTimeout(pending.timer);
  if(response.deviceId&&response.deviceId!==pending.deviceId){
    pending.reject(new Error("hardware_device_mismatch"));return;
  }
  if(response.error){pending.reject(new Error(String(response.error)));return;}
  if(!response.signature){pending.reject(new Error("hardware_signature_invalid"));return;}
  pending.resolve(String(response.signature));
});
ipcMain.handle("vault:reveal-location",()=>{
  const path=ensureVaultPath();
  if(existsSync(path))shell.showItemInFolder(path);
  else shell.openPath(dirname(path));
  return path;
});

app.whenReady().then(()=>{
  ensureVaultPath();
  // Electron's OS session notifications are not browser heuristics.
  powerMonitor.on("lock-screen",lockIdentity);
  powerMonitor.on("suspend",lockIdentity);
  tryAutoUnlockInstalled();
  startPresenceMonitor();
  startBridge();
  createWindow();
  app.on("activate",()=>{if(BrowserWindow.getAllWindows().length===0)createWindow();});
});
app.on("window-all-closed",()=>{if(process.platform!=="darwin")app.quit();});
app.on("before-quit",()=>{
  if(presenceTimer)clearInterval(presenceTimer);
  for(const pending of pendingHardwareSigns.values()){
    clearTimeout(pending.timer);
    pending.reject(new Error("hardware_bridge_closed"));
  }
  pendingHardwareSigns.clear();
  bridge?.close();
  lockIdentity();
});
