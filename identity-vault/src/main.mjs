import {app,BrowserWindow,dialog,ipcMain,safeStorage,shell} from "electron";
import {createServer} from "node:http";
import {createHash,createPublicKey} from "node:crypto";
import {copyFileSync,existsSync,mkdirSync,readFileSync,unlinkSync,writeFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
import {generateIdentity,generateUsbUnlockToken,encryptPortable,decryptPortableRecord,normalizeIdentityProfile,assertionPayload,signAssertion} from "./vault-core.mjs";

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
  "https://xdsawyerlol.github.io"
]);

let vaultPath="";
let activeIdentity=null;
let bridge=null;
let bridgeError="";
let presenceTimer=null;
let hardwarePermissionConfigured=false;
const pendingHardwareSigns=new Map();

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
  writeFileSync(path,JSON.stringify(record,null,2),{encoding:"utf8",mode:0o600});
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
  if(record?.mode!=="portable"||record?.unlockMode!=="usb-presence")return false;
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
  if(activeIdentity&&record?.mode==="portable"&&record?.unlockMode==="usb-presence"&&!usbPresenceAvailable(record)){
    activeIdentity=null;
  }
  const hardwareMode=record?.unlockMode===HARDWARE_UNLOCK_MODE;
  const legacyVault=Boolean(record?.mode==="portable"&&!["usb-presence",HARDWARE_UNLOCK_MODE].includes(record?.unlockMode));
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
    keyId:activeIdentity?.keyId||record?.keyId||null,
    label:activeIdentity?.label||record?.label||null,
    publicKey:activeIdentity?.publicKey||record?.publicKey||null,
    profile:activeIdentity?.profile||null,
    profileAvailable:Boolean(activeIdentity?.profile),
    formatVersion:Number(record?.version||1),
    vaultPath:ensureVaultPath()
  };
}

function createIdentity({label="",profile={}}={}){
  const normalizedProfile=normalizeIdentityProfile(profile);
  const suggestedLabel=normalizedProfile.preferredName||[normalizedProfile.firstName,normalizedProfile.lastName].filter(Boolean).join(" ");
  const identity=generateIdentity(label||suggestedLabel||"Mon identité Quantic");
  const createdAt=new Date().toISOString();
  const secret=secretPayload(identity.privateKeyPem,normalizedProfile);

  if(isPortable){
    const target=ensureVaultPath();
    backupExistingPortableVault(target);
    const token=generateUsbUnlockToken();
    const encryptedSecret=encryptPortable(secret,token);
    writeFileSync(keyPathFor(target),token,{encoding:"utf8",mode:0o600});
    saveRecord({
      version:5,
      mode:"portable",
      unlockMode:"usb-presence",
      algorithm:"ed25519",
      keyId:identity.keyId,
      label:identity.label,
      publicKey:identity.publicKey,
      encryptedSecret,
      createdAt
    });
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

function unlockIdentity(){
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
  if(record.unlockMode===HARDWARE_UNLOCK_MODE)throw new Error("hardware_unlock_required");
  let secretValue="";
  if(record.mode==="portable"){
    if(record.unlockMode!=="usb-presence")throw new Error("legacy_vault_requires_code");
    try{
      secretValue=decryptPortableRecord(record,readUsbUnlockToken(record));
    }catch(error){
      const code=String(error?.message||error);
      if(["usb_key_missing","usb_key_invalid"].includes(code))throw error;
      throw new Error("usb_vault_unlock_failed");
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

function updateProfile(profile={},hardwareVaultKey=""){
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
    if(record.unlockMode!=="usb-presence")throw new Error("legacy_vault_requires_code");
    encryptedSecret=encryptPortable(secret,readUsbUnlockToken(record));
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
  return publicStatus();
}

function lockIdentity(){
  activeIdentity=null;
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
    const record=loadRecord();
    if(!record||(record.mode==="portable"&&record.unlockMode==="usb-presence"&&!usbPresenceAvailable(record))){
      activeIdentity=null;
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
        keyId:status.keyId,
        label:status.label,
        publicKey:status.publicKey,
        algorithm:status.keyAlgorithm,
        hardwareMode:status.hardwareMode,
        vaultMode:status.vaultMode
      },cors);
    }
    if(url.pathname==="/v1/assert"&&req.method==="POST"){
      if(!activeIdentity)return json(res,423,{error:"identity_locked"},cors);
      try{
        const body=await readJsonBody(req);
        const input={
          keyId:activeIdentity.keyId,
          challenge:body.challenge,
          audience:body.audience||origin||""
        };
        if(activeIdentity.algorithm===HARDWARE_ALGORITHM){
          const payload=assertionPayload(input);
          const signature=await requestHardwareSignature(payload,activeIdentity.hardwareDeviceId);
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
ipcMain.handle("vault:unlock",()=>unlockIdentity());
ipcMain.handle("vault:unlock-hardware",(_event,options)=>unlockHardwareIdentity(options||{}));
ipcMain.handle("vault:update-profile",(_event,{profile,hardwareVaultKey}={})=>updateProfile(profile||{},hardwareVaultKey||""));
ipcMain.handle("vault:lock",()=>lockIdentity());
ipcMain.handle("vault:hardware-disconnected",(_event,{deviceId}={})=>{
  if(activeIdentity?.algorithm===HARDWARE_ALGORITHM&&(!deviceId||deviceId===activeIdentity.hardwareDeviceId))activeIdentity=null;
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
  activeIdentity=null;
});
