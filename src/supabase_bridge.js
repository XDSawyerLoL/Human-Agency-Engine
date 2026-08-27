import { config } from './config.js';

const cleanBase=value=>String(value||'').trim().replace(/\/+$/,'');

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
      'content-type':'application/json',
      accept:'application/json',
      ...extra
    };
  }

  async request(path,{method='GET',body=null,headers={}}={}){
    if(!this.enabled) throw new Error('supabase_not_configured');
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),8_000);
    try{
      const response=await fetch(`${this.url}${path}`,{
        method,
        headers:this.headers(headers),
        body:body===null?undefined:JSON.stringify(body),
        signal:controller.signal
      });
      if(!response.ok){
        const text=await response.text().catch(()=>String(response.status));
        throw new Error(`supabase_http_${response.status}:${text.slice(0,180)}`);
      }
      if(response.status===204) return null;
      const text=await response.text();
      return text?JSON.parse(text):null;
    } finally { clearTimeout(timer); }
  }

  async writeState(stateKey,payload){
    if(!this.enabled) return {ok:false,skipped:true};
    try{
      await this.request('/rest/v1/evidence_runtime_state?on_conflict=state_key',{
        method:'POST',
        headers:{Prefer:'resolution=merge-duplicates,return=minimal'},
        body:[{state_key:String(stateKey).slice(0,96),payload,updated_at:new Date().toISOString()}]
      });
      this.lastWriteAt=new Date().toISOString();
      this.lastError=null;
      return {ok:true};
    } catch(error){
      this.lastError=String(error?.message||error);
      console.error('[supabase]',this.lastError);
      return {ok:false,error:this.lastError};
    }
  }

  async readState(stateKey){
    if(!this.enabled) return null;
    const key=encodeURIComponent(String(stateKey));
    const rows=await this.request(`/rest/v1/evidence_runtime_state?state_key=eq.${key}&select=payload,updated_at&limit=1`);
    return Array.isArray(rows)&&rows.length?rows[0]:null;
  }

  async health(){
    if(!this.enabled) return {configured:false,connected:false,last_write_at:this.lastWriteAt,last_error:this.lastError};
    try{
      await this.request('/rest/v1/evidence_runtime_state?select=state_key,updated_at&limit=1');
      this.lastError=null;
      return {configured:true,connected:true,last_write_at:this.lastWriteAt,last_error:null};
    }catch(error){
      this.lastError=String(error?.message||error);
      return {configured:true,connected:false,last_write_at:this.lastWriteAt,last_error:this.lastError};
    }
  }
}

export async function mirrorV11State(bridge,{snapshot=null,causalLearning=null,sports=null}={}){
  if(!bridge?.enabled) return {configured:false,writes:[]};
  const writes=[];
  if(snapshot) writes.push(['latest_snapshot',await bridge.writeState('latest_snapshot',snapshot)]);
  if(causalLearning) writes.push(['causal_learning',await bridge.writeState('causal_learning',causalLearning)]);
  if(sports) writes.push(['sports_intelligence',await bridge.writeState('sports_intelligence',sports)]);
  return {configured:true,writes:writes.map(([key,result])=>({key,...result}))};
}
