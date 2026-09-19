import {app,BrowserWindow,ipcMain,safeStorage,shell} from "electron";
import {createServer} from "node:http";
import {existsSync,mkdirSync,readFileSync,writeFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
import {generateIdentity,encryptPortable,decryptPortable,signAssertion} from "./vault-core.mjs";

const __dirname=dirname(fileURLToPath(import.meta.url));
const HOST="127.0.0.1";
const PORT=47621;
const isPortable=Boolean(process.env.PORTABLE_EXECUTABLE_DIR);
const allowedOrigins=new Set([
  "https://mediumorchid-badger-314305.hostingersite.com",
  "https://xdsawyerlol.github.io"
]);

let vaultPath="";
let activeIdentity=null;
let bridge=null;
let bridgeError="";

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

function ensureVaultPath(){
  const dir=vaultDirectory();
  mkdirSync(dir,{recursive:true});
  vaultPath=join(dir,"identity-vault.json");
  return vaultPath;
}

function loadRecord(){
  ensureVaultPath();
  if(!existsSync(vaultPath))return null;
  try{return JSON.parse(readFileSync(vaultPath,"utf8"))}catch{return null}
}

function saveRecord(record){
  ensureVaultPath();
  writeFileSync(vaultPath,JSON.stringify(record,null,2),{encoding:"utf8",mode:0o600});
}

function publicStatus(){
  const record=loadRecord();
  return {
    product:"Quantic Identity Vault",
    version:1,
    bridge:{host:HOST,port:PORT,ready:Boolean(bridge),error:bridgeError||null},
    vaultMode:isPortable?"portable":"pc",
    keyAlgorithm:"ed25519",
    portableCipher:"aes-256-gcm",
    vaultExists:Boolean(record),
    identityAvailable:Boolean(activeIdentity),
    keyId:activeIdentity?.keyId||record?.keyId||null,
    label:activeIdentity?.label||record?.label||null,
    publicKey:activeIdentity?.publicKey||record?.publicKey||null,
    vaultPath
  };
}

function createIdentity({label="",passphrase=""}={}){
  const identity=generateIdentity(label||"Mon identité Quantic");
  if(isPortable){
    const encryptedPrivateKey=encryptPortable(identity.privateKeyPem,passphrase);
    saveRecord({version:1,mode:"portable",keyId:identity.keyId,label:identity.label,publicKey:identity.publicKey,encryptedPrivateKey,createdAt:new Date().toISOString()});
  }else{
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    const encryptedPrivateKey=safeStorage.encryptString(identity.privateKeyPem).toString("base64");
    saveRecord({version:1,mode:"pc",keyId:identity.keyId,label:identity.label,publicKey:identity.publicKey,encryptedPrivateKey,createdAt:new Date().toISOString()});
  }
  activeIdentity=identity;
  return publicStatus();
}

function unlockIdentity(passphrase=""){
  const record=loadRecord();
  if(!record)throw new Error("vault_not_found");
  let privateKeyPem="";
  if(record.mode==="portable"){
    privateKeyPem=decryptPortable(record.encryptedPrivateKey,passphrase);
  }else if(record.mode==="pc"){
    if(!safeStorage.isEncryptionAvailable())throw new Error("system_encryption_unavailable");
    privateKeyPem=safeStorage.decryptString(Buffer.from(record.encryptedPrivateKey,"base64"));
  }else{
    throw new Error("vault_format_invalid");
  }
  activeIdentity={keyId:record.keyId,label:record.label,publicKey:record.publicKey,privateKeyPem};
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
  try{unlockIdentity("")}catch{}
}

function startBridge(){
  if(bridge)return;
  bridge=createServer(async(req,res)=>{
    const origin=String(req.headers.origin||"");
    const cors=corsHeaders(origin);
    if(!cors){
      return json(res,403,{error:"origin_not_allowed"});
    }
    if(req.method==="OPTIONS"){
      res.writeHead(204,cors);res.end();return;
    }
    const url=new URL(req.url||"/","http://"+HOST+":"+PORT);
    if(url.pathname==="/v1/status"&&req.method==="GET"){
      const status=publicStatus();
      return json(res,200,{
        version:1,
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
        return json(res,200,{
          version:1,
          keyId:activeIdentity.keyId,
          publicKey:activeIdentity.publicKey,
          ...assertion
        },cors);
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
    width:900,
    height:680,
    minWidth:720,
    minHeight:560,
    backgroundColor:"#f5f7f9",
    title:"Quantic Identity Vault",
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
ipcMain.handle("vault:unlock",(_event,{passphrase}={})=>unlockIdentity(passphrase||""));
ipcMain.handle("vault:lock",()=>lockIdentity());
ipcMain.handle("vault:reveal-location",()=>{
  ensureVaultPath();
  if(existsSync(vaultPath))shell.showItemInFolder(vaultPath);
  else shell.openPath(vaultDirectory());
  return vaultPath;
});

app.whenReady().then(()=>{
  ensureVaultPath();
  tryAutoUnlockInstalled();
  startBridge();
  createWindow();
  app.on("activate",()=>{if(BrowserWindow.getAllWindows().length===0)createWindow();});
});
app.on("window-all-closed",()=>{if(process.platform!=="darwin")app.quit();});
app.on("before-quit",()=>{bridge?.close();activeIdentity=null;});
