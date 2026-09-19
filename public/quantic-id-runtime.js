(()=>{'use strict';
const BRIDGE_ORIGIN='http://127.0.0.1:47621';
const STATUS_URL=BRIDGE_ORIGIN+'/v1/status';

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

    if(version!==1){
      return {ok:false,installed:true,identityAvailable:false,reason:'unsupported_version',version};
    }
    if(!identityAvailable){
      return {ok:false,installed:true,identityAvailable:false,reason:'identity_inactive',version,label};
    }
    if(!keyId){
      return {ok:false,installed:true,identityAvailable:false,reason:'invalid_identity_status',version,label};
    }
    return {ok:true,installed:true,identityAvailable:true,version,keyId,label};
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

window.QuanticID=Object.freeze({
  bridgeOrigin:BRIDGE_ORIGIN,
  statusUrl:STATUS_URL,
  probe
});
})();