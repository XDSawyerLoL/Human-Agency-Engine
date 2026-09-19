(()=>{'use strict';
const BRIDGE_ORIGIN='http://127.0.0.1:47621';
const STATUS_URL=BRIDGE_ORIGIN+'/v1/status';
const ASSERT_URL=BRIDGE_ORIGIN+'/v1/assert';
const SUPPORTED_STATUS_VERSIONS=new Set([1,2,3]);

async function probe({timeoutMs=1200}={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const response=await fetch(STATUS_URL,{
      method:'GET',
      cache:'no-store',
      credentials:'omit',
      headers:{Accept:'application/json'},
      signal:controller.signal
    });
    if(!response.ok){
      return {ok:false,installed:true,identityAvailable:false,reason:'bridge_http_'+response.status};
    }
    const data=await response.json();
    const version=Number(data?.version??0);
    const identityAvailable=data?.identityAvailable===true;
    const keyId=typeof data?.keyId==='string'?data.keyId.trim():'';
    const label=typeof data?.label==='string'&&data.label.trim()?data.label.trim():'Quantic ID';

    if(!SUPPORTED_STATUS_VERSIONS.has(version)){
      return {ok:false,installed:true,identityAvailable:false,reason:'unsupported_version',version};
    }
    if(!identityAvailable){
      return {ok:false,installed:true,identityAvailable:false,reason:'identity_inactive',version,label};
    }
    if(!keyId){
      return {ok:false,installed:true,identityAvailable:false,reason:'invalid_identity_status',version,label};
    }
    return {ok:true,installed:true,identityAvailable:true,version,keyId,label,appVersion:typeof data?.appVersion==='string'?data.appVersion:''};
  }catch(error){
    const aborted=error?.name==='AbortError';
    return {
      ok:false,
      installed:false,
      identityAvailable:false,
      reason:aborted?'bridge_timeout':'bridge_unavailable'
    };
  }finally{
    clearTimeout(timer);
  }
}

async function assert({challenge,audience='',timeoutMs=2500}={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const response=await fetch(ASSERT_URL,{
      method:'POST',
      cache:'no-store',
      credentials:'omit',
      headers:{'Content-Type':'application/json','Accept':'application/json'},
      body:JSON.stringify({challenge:String(challenge||''),audience:String(audience||'')}),
      signal:controller.signal
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      const error=new Error(data.error||('bridge_http_'+response.status));
      error.data=data;
      throw error;
    }
    if(Number(data.version)!==1||!data.keyId||!data.publicKey||!data.payload||!data.signature){
      throw new Error('invalid_identity_assertion');
    }
    return data;
  }finally{
    clearTimeout(timer);
  }
}

window.QuanticID=Object.freeze({
  bridgeOrigin:BRIDGE_ORIGIN,
  statusUrl:STATUS_URL,
  assertUrl:ASSERT_URL,
  probe,
  assert
});
})();