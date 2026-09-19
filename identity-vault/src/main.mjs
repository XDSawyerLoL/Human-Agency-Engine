import {app,BrowserWindow,dialog,ipcMain,safeStorage,shell} from "electron";
import {createServer} from "node:http";
import {copyFileSync,existsSync,mkdirSync,readFileSync,writeFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
import {generateIdentity,generateUsbUnlockToken,encryptPortable,decryptPortableRecord,normalizeIdentityProfile,signAssertion} from "./vault-core.mjs";

const __dirname=dirname(fileURLToPath(import.meta.url));
const HOST="127.0.0.1";
const PORT=47621;
const USB_KEY_FILENAME="identity-vault.key";
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

function validateRecord(record){
  if(!record||typeof record!=="object")throw new Error("vault_format_invalid");
  if(!["portable","pc"].includes(record.mode))throw new Error("vault_format_invalid");
  if(!record.keyId||!record.publicKey)throw new Error("vault_format_invalid");
  if(!record.encryptedSecret&&!record.encryptedPrivateKey)throw new Error("vault_format_invalid");
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

function backupExistingPortableVault(){
  const target=defaultVaultPath();
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
    version:3,
    privateKeyPem:String(privateKeyPem),
    profile:normalizeIdentityProfile(profile)
  });
}

function parseSecret(value){
  const raw=String(value||"");
  try{
    const parsed=JSON.parse(raw);
    if(parsed?.privateKeyPem){
      return {privateKeyPem:String(parsed.privateKeyPem),profile:normalizeIdentityProfile(parsed.profile||{})};
    }
  }catch{}
  return {privateKeyPem:raw,profile:normalizeIdentityProfile({})};
}

function publicStatus(){
  const record=loadRecord();
  if(activeIdentity&&record?.mode==="portable"&&record?.unlockMode==="usb-presence"&&!usbPresenceAvailable(record)){
    activeIdentity=null;
  }
  const legacyVault=Boolean(record?.mode==="portable"&&record?.unlockMode!=="usb-presence");
  return {
    product:"Quantic Identity Vault",
    version:3,
    appVersion:app.getVersion(),
    bridge:{host:HOST,port:PORT,ready:Boolean(bridge),error:bridgeError||null},
    vaultMode:record?.mode||(isPortable?"portable":"pc"),
    unlockMode:record?.unlockMode||(record?.mode==="portable"?"legacy-code":"system"),
    keyAlgorithm:"ed25519",
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
    backupExistingPortableVault();
    vaultPath=defaultVaultPath();
    const token=generateUsbUnlockToken();
    const encryptedSecret=encryptPortable(secret,token);
    writeFileSync(keyPathFor(),token,{encoding:"utf8",mode:0o600});
    saveRecord({
      version:3,
      mode:"portable",
      unlockMode:"usb-presence",
      keyId:identity.keyId,
      label:identity.label,
      publicKey:identity.publicKey,
      encryptedSecret,
      createdAt
    });
    activeIdentity={...identity,profile:normalizedProfile};
  }else{
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    const encryptedSecret=safeStorage.encryptString(secret).toString("base64");
    saveRecord({version:3,mode:"pc",unlockMode:"system",keyId:identity.keyId,label:identity.label,publicKey:identity.publicKey,encryptedSecret,createdAt});
    activeIdentity={...identity,profile:normalizedProfile};
  }
  return publicStatus();
}

function unlockIdentity(){
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
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
    privateKeyPem:secret.privateKeyPem,
    profile:secret.profile
  };
  return publicStatus();
}

function updateProfile(profile={}){
  if(!activeIdentity)throw new Error("identity_locked");
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
  const normalizedProfile=normalizeIdentityProfile(profile);
  const nextLabel=normalizedProfile.preferredName||[normalizedProfile.firstName,normalizedProfile.lastName].filter(Boolean).join(" ")||record.label||activeIdentity.label;
  const secret=secretPayload(activeIdentity.privateKeyPem,normalizedProfile);
  let encryptedSecret;

  if(record.mode==="portable"){
    if(record.unlockMode!=="usb-presence")throw new Error("legacy_vault_requires_code");
    encryptedSecret=encryptPortable(secret,readUsbUnlockToken(record));
  }else{
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    encryptedSecret=safeStorage.encryptString(secret).toString("base64");
  }

  const next={
    version:3,
    mode:record.mode,
    unlockMode:record.mode==="portable"?"usb-presence":"system",
    keyId:record.keyId,
    label:nextLabel,
    publicKey:record.publicKey,
    encryptedSecret,
    createdAt:record.createdAt||new Date().toISOString(),
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
        version:3,
        product:"Quantic Identity Vault",
        identityAvailable:status.identityAvailable,
        keyId:status.keyId,
        label:status.label,
        publicKey:status.publicKey,
        vaultMode:status.vaultMode
      },cors);
    }
    if(url.pathname==="/v1/assert"&&req.method==="POST"){
      if(!activeIdentity)return json(res,423,{error:"identity_locked"},cors);
      try{
        const body=await readJsonBody(req);
        const assertion=signAssertion(activeIdentity.privateKeyPem,{
          keyId:activeIdentity.keyId,
          challenge:body.challenge,
          audience:body.audience||origin||""
        });
        return json(res,200,{version:1,keyId:activeIdentity.keyId,publicKey:activeIdentity.publicKey,...assertion},cors);
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
    height:820,
    minWidth:760,
    minHeight:620,
    backgroundColor:"#f5f7f9",
    title:`Quantic Identity Vault ${app.getVersion()}`,
    webPreferences:{
      preload:join(__dirname,"preload.cjs"),
      contextIsolation:true,
      nodeIntegration:false,
      sandbox:true
    }
  });
  win.removeMenu();
  win.loadFile(join(__dirname,"index.html"));
}

ipcMain.handle("vault:status",()=>publicStatus());
ipcMain.handle("vault:create",(_event,options)=>createIdentity(options||{}));
ipcMain.handle("vault:load-file",()=>loadVaultFile());
ipcMain.handle("vault:unlock",()=>unlockIdentity());
ipcMain.handle("vault:update-profile",(_event,{profile}={})=>updateProfile(profile||{}));
ipcMain.handle("vault:lock",()=>lockIdentity());
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
  bridge?.close();
  activeIdentity=null;
});
