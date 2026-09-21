import https from 'node:https';
import { config } from './config.js';

const cleanBase=value=>String(value||'').trim().replace(/\/+$/,'');

function wait(ms){return new Promise(resolve=>setTimeout(resolve,ms))}

export class SupabaseBridge {
  constructor(){
    this.url=cleanBase(config.supabase?.url);
    this.key=String(config.supabase?.secretKey||'').trim();
    this.enabled=Boolean(this.url&&this.key);
    this.lastWriteAt=null;
    this.lastError=null;
  }

  headers(extra={}){
    return {
      apikey:this.key,
      authorization:`Bearer ${this.key}`,
      'content-type':'application/json',
      accept:'application/json',
      ...extra
    };
  }

  async fetchRequest(url,{method,body,headers}){
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),8_000);
    try{
      const response=await fetch(url,{
        method,
        headers,
        body,
        signal:controller.signal,
        redirect:'error'
      });
      const text=await response.text();
      if(!response.ok)throw new Error(`supabase_http_${response.status}:${text.slice(0,180)}`);
      return response.status===204?null:(text?JSON.parse(text):null);
    }finally{clearTimeout(timer)}
  }

  async httpsRequest(url,{method,body,headers}){
    const target=new URL(url);
    if(target.protocol!=='https:')throw new Error('supabase_https_required');
    return new Promise((resolve,reject)=>{
      const request=https.request({
        protocol:'https:',
        hostname:target.hostname,
        port:target.port||443,
        path:target.pathname+target.search,
        method,
        family:4,
        headers:{
          ...headers,
          ...(body?{'content-length':Buffer.byteLength(body)}:{})
        },
        timeout:8_000
      },response=>{
        const chunks=[];
        response.on('data',chunk=>chunks.push(chunk));
        response.on('end',()=>{
          const text=Buffer.concat(chunks).toString('utf8');
          const status=Number(response.statusCode||0);
          if(status<200||status>=300){
            reject(new Error(`supabase_http_${status}:${text.slice(0,180)}`));
            return;
          }
          try{resolve(status===204?null:(text?JSON.parse(text):null))}
          catch{reject(new Error('supabase_invalid_json'))}
        });
      });
      request.on('timeout',()=>request.destroy(new Error('supabase_timeout')));
      request.on('error',reject);
      if(body)request.write(body);
      request.end();
    });
  }

  async request(path,{method='GET',body=null,headers={}}={}){
    if(!this.enabled)throw new Error('supabase_not_configured');
    const url=`${this.url}${path}`;
    const requestHeaders=this.headers(headers);
    const payload=body===null?undefined:JSON.stringify(body);
    let lastError=null;

    for(let attempt=0;attempt<3;attempt++){
      try{
        return await this.fetchRequest(url,{method,body:payload,headers:requestHeaders});
      }catch(error){
        lastError=error;
        const message=String(error?.message||error);
        if(/^supabase_http_4\d\d/.test(message)&&!message.startsWith('supabase_http_408')&&!message.startsWith('supabase_http_429'))throw error;
        if(attempt<2)await wait(250*(attempt+1));
      }
    }

    // Some shared-hosting Node runtimes intermittently fail inside undici/fetch.
    // Retry through the native HTTPS stack and force IPv4 before declaring storage unavailable.
    try{
      return await this.httpsRequest(url,{method,body:payload,headers:requestHeaders});
    }catch(error){
      const detail=String(error?.message||error);
      const first=String(lastError?.message||lastError||'fetch_failed');
      throw new Error(`supabase_transport_failed:${first};fallback:${detail}`);
    }
  }

  async writeState(stateKey,payload){
    if(!this.enabled)return{ok:false,skipped:true};
    try{
      await this.request('/rest/v1/evidence_runtime_state?on_conflict=state_key',{
        method:'POST',
        headers:{Prefer:'resolution=merge-duplicates,return=minimal'},
        body:[{state_key:String(stateKey).slice(0,96),payload,updated_at:new Date().toISOString()}]
      });
      this.lastWriteAt=new Date().toISOString();
      this.lastError=null;
      return{ok:true};
    }catch(error){
      this.lastError=String(error?.message||error);
      console.error('[supabase]',this.lastError);
      return{ok:false,error:this.lastError};
    }
  }

  async readState(stateKey){
    if(!this.enabled)return null;
    const key=encodeURIComponent(String(stateKey));
    const rows=await this.request(`/rest/v1/evidence_runtime_state?state_key=eq.${key}&select=payload,updated_at&limit=1`);
    return Array.isArray(rows)&&rows.length?rows[0]:null;
  }

  async health(){
    if(!this.enabled)return{configured:false,connected:false,last_write_at:this.lastWriteAt,last_error:this.lastError};
    try{
      await this.request('/rest/v1/evidence_runtime_state?select=state_key,updated_at&limit=1');
      this.lastError=null;
      return{configured:true,connected:true,last_write_at:this.lastWriteAt,last_error:null};
    }catch(error){
      this.lastError=String(error?.message||error);
      return{configured:true,connected:false,last_write_at:this.lastWriteAt,last_error:this.lastError};
    }
  }
}

export async function mirrorV11State(bridge,{snapshot=null,causalLearning=null,sports=null}={}){
  if(!bridge?.enabled)return{configured:false,writes:[]};
  const writes=[];
  if(snapshot)writes.push(['latest_snapshot',await bridge.writeState('latest_snapshot',snapshot)]);
  if(causalLearning)writes.push(['causal_learning',await bridge.writeState('causal_learning',causalLearning)]);
  if(sports)writes.push(['sports_intelligence',await bridge.writeState('sports_intelligence',sports)]);
  return{configured:true,writes:writes.map(([key,result])=>({key,...result}))};
}
