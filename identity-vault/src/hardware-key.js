(()=>{'use strict';

const VENDOR_ID=0xcafe;
const PRODUCT_ID=0x5148;
const REPORT_ID=1;
const REPORT_BYTES=64;
const HEADER_BYTES=11;
const PAYLOAD_BYTES=REPORT_BYTES-HEADER_BYTES;
const MAGIC=[0x51,0x48,0x4b,0x31];
const PROTOCOL_VERSION=1;
const COMMANDS=Object.freeze({INFO:1,PROVISION:2,UNLOCK:3,SIGN:4});
const ALGORITHM='ecdsa-p256-sha256';
const enc=new TextEncoder();
const dec=new TextDecoder();

function b64url(bytes){
  let binary='';
  const data=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes);
  for(let i=0;i<data.length;i++)binary+=String.fromCharCode(data[i]);
  return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function fromB64url(value){
  const normalized=String(value||'').replace(/-/g,'+').replace(/_/g,'/');
  const padded=normalized+'='.repeat((4-normalized.length%4)%4);
  const raw=atob(padded);
  const out=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);
  return out;
}
function concat(parts){
  const size=parts.reduce((n,p)=>n+p.length,0);
  const out=new Uint8Array(size);
  let offset=0;
  for(const part of parts){out.set(part,offset);offset+=part.length;}
  return out;
}
function spkiFromRawP256(rawValue){
  const raw=typeof rawValue==='string'?fromB64url(rawValue):new Uint8Array(rawValue);
  if(raw.length!==65||raw[0]!==4)throw new Error('hardware_public_key_invalid');
  const header=Uint8Array.from([
    0x30,0x59,0x30,0x13,0x06,0x07,0x2a,0x86,0x48,0xce,0x3d,0x02,0x01,
    0x06,0x08,0x2a,0x86,0x48,0xce,0x3d,0x03,0x01,0x07,0x03,0x42,0x00
  ]);
  return concat([header,raw]);
}
async function keyIdFromSpki(spki){
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',spki));
  return 'qid_'+[...digest.slice(0,16)].map(v=>v.toString(16).padStart(2,'0')).join('');
}
function packet(command,requestId,index,total,payload){
  const out=new Uint8Array(REPORT_BYTES);
  out.set(MAGIC,0);
  out[4]=PROTOCOL_VERSION;
  out[5]=command;
  out[6]=requestId&255;
  out[7]=(requestId>>8)&255;
  out[8]=index;
  out[9]=total;
  out[10]=payload.length;
  out.set(payload,HEADER_BYTES);
  return out;
}
function parsePacket(data){
  const bytes=new Uint8Array(data.buffer,data.byteOffset,data.byteLength);
  if(bytes.length<HEADER_BYTES)return null;
  for(let i=0;i<4;i++)if(bytes[i]!==MAGIC[i])return null;
  if(bytes[4]!==PROTOCOL_VERSION)return null;
  const length=bytes[10];
  if(length>PAYLOAD_BYTES)return null;
  return {
    command:bytes[5],
    requestId:bytes[6]|(bytes[7]<<8),
    index:bytes[8],
    total:bytes[9],
    payload:bytes.slice(HEADER_BYTES,HEADER_BYTES+length)
  };
}

class QuanticHardwareClient{
  constructor(){
    this.device=null;
    this.pending=new Map();
    this.sequence=1;
    this.boundReport=event=>this.onReport(event);
  }
  supported(){return Boolean(navigator.hid)}
  matches(device){
    return device?.vendorId===VENDOR_ID&&device?.productId===PRODUCT_ID;
  }
  async attach(device){
    if(!device||!this.matches(device))throw new Error('hardware_device_invalid');
    if(this.device&&this.device!==device){
      try{this.device.removeEventListener('inputreport',this.boundReport)}catch{}
    }
    this.device=device;
    if(!device.opened)await device.open();
    device.removeEventListener('inputreport',this.boundReport);
    device.addEventListener('inputreport',this.boundReport);
    return this.info();
  }
  async pair(){
    if(!this.supported())throw new Error('hardware_webhid_unavailable');
    const devices=await navigator.hid.requestDevice({filters:[{vendorId:VENDOR_ID,productId:PRODUCT_ID}]});
    if(!devices?.length)throw new Error('hardware_device_not_selected');
    return this.attach(devices[0]);
  }
  async reconnect(deviceId=''){
    if(!this.supported())throw new Error('hardware_webhid_unavailable');
    const devices=await navigator.hid.getDevices();
    const matching=devices.filter(device=>this.matches(device));
    if(!matching.length)throw new Error('hardware_device_not_paired');
    for(const device of matching){
      try{
        const info=await this.attach(device);
        if(!deviceId||info.deviceId===deviceId)return info;
      }catch{}
    }
    throw new Error('hardware_device_mismatch');
  }
  async ensure(deviceId=''){
    if(this.device?.opened){
      const info=await this.info();
      if(!deviceId||info.deviceId===deviceId)return info;
    }
    return this.reconnect(deviceId);
  }
  onReport(event){
    if(event.reportId!==REPORT_ID)return;
    const frame=parsePacket(event.data);
    if(!frame)return;
    const pending=this.pending.get(frame.requestId);
    if(!pending||frame.command!==(pending.command|0x80))return;
    if(!pending.parts.length)pending.parts=Array(frame.total).fill(null);
    if(frame.total!==pending.parts.length||frame.index>=frame.total)return;
    pending.parts[frame.index]=frame.payload;
    if(pending.parts.some(part=>part===null))return;
    this.pending.delete(frame.requestId);
    clearTimeout(pending.timer);
    try{
      const body=JSON.parse(dec.decode(concat(pending.parts)));
      if(body?.error)pending.reject(new Error(String(body.error)));
      else pending.resolve(body);
    }catch(error){pending.reject(error)}
  }
  async request(command,body={},timeoutMs=7000){
    if(!this.device?.opened)throw new Error('hardware_device_not_open');
    const payload=enc.encode(JSON.stringify(body));
    const total=Math.max(1,Math.ceil(payload.length/PAYLOAD_BYTES));
    if(total>255)throw new Error('hardware_request_too_large');
    const requestId=this.sequence=(this.sequence%65534)+1;
    const promise=new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{
        this.pending.delete(requestId);
        reject(new Error('hardware_request_timeout'));
      },timeoutMs);
      this.pending.set(requestId,{command,parts:[],resolve,reject,timer});
    });
    for(let index=0;index<total;index++){
      const part=payload.slice(index*PAYLOAD_BYTES,(index+1)*PAYLOAD_BYTES);
      await this.device.sendReport(REPORT_ID,packet(command,requestId,index,total,part));
    }
    return promise;
  }
  async info(){
    const info=await this.request(COMMANDS.INFO,{});
    if(Number(info.protocol)!==PROTOCOL_VERSION||!info.deviceId)throw new Error('hardware_protocol_invalid');
    return info;
  }
  async provision(){
    const result=await this.request(COMMANDS.PROVISION,{algorithm:ALGORITHM},15000);
    if(!result.deviceId||!result.publicKeyRaw||!result.vaultKey)throw new Error('hardware_provision_invalid');
    const spki=spkiFromRawP256(result.publicKeyRaw);
    return {
      deviceId:String(result.deviceId),
      algorithm:ALGORITHM,
      publicKey:b64url(spki),
      keyId:await keyIdFromSpki(spki),
      vaultKey:String(result.vaultKey)
    };
  }
  async unlock(deviceId=''){
    await this.ensure(deviceId);
    const result=await this.request(COMMANDS.UNLOCK,{});
    if(!result.deviceId||!result.vaultKey)throw new Error('hardware_unlock_invalid');
    if(deviceId&&result.deviceId!==deviceId)throw new Error('hardware_device_mismatch');
    return {deviceId:String(result.deviceId),vaultKey:String(result.vaultKey)};
  }
  async sign(payload,deviceId=''){
    await this.ensure(deviceId);
    const result=await this.request(COMMANDS.SIGN,{payload:String(payload||'')},10000);
    if(!result.signature)throw new Error('hardware_signature_invalid');
    return String(result.signature);
  }
}

const client=new QuanticHardwareClient();
window.QuanticHardware=Object.freeze({
  vendorId:VENDOR_ID,
  productId:PRODUCT_ID,
  algorithm:ALGORITHM,
  supported:()=>client.supported(),
  pair:()=>client.pair(),
  reconnect:deviceId=>client.reconnect(deviceId),
  provision:()=>client.provision(),
  unlock:deviceId=>client.unlock(deviceId),
  sign:(payload,deviceId)=>client.sign(payload,deviceId)
});

if(navigator.hid){
  navigator.hid.addEventListener('disconnect',event=>{
    window.dispatchEvent(new CustomEvent('quantic-hardware-disconnect',{detail:{vendorId:event.device.vendorId,productId:event.device.productId}}));
  });
}
})();