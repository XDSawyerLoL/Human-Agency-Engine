export const QUANTIC_SERVICE_TARGETS = Object.freeze([
  Object.freeze({ id:'vision', label:'Quantic Vision', kind:'vision', public_url:'/vision/', probe_url:null, state:'active' }),
  Object.freeze({ id:'mail', label:'Quantic Mail', kind:'application', public_url:'https://quanticmail.onrender.com', probe_url:'https://quanticmail.onrender.com', state:'active' }),
  Object.freeze({ id:'relay-render', label:'Quantic Relay · Render', kind:'relay', public_url:'https://quanticmail-network-relay.onrender.com', probe_url:'https://quanticmail-network-relay.onrender.com', state:'active' }),
  Object.freeze({ id:'relay-railway', label:'Quantic Relay · Railway', kind:'relay', public_url:'https://quantic-network-relay-backup-production.up.railway.app', probe_url:'https://quantic-network-relay-backup-production.up.railway.app', state:'active' }),
  Object.freeze({ id:'relay-hostinger', label:'Quantic Relay · Hostinger', kind:'relay', public_url:'/network/', probe_url:null, state:'pending' })
]);

export async function probeQuanticService(target,{timeoutMs=2500,fetchImpl=fetch}={}){
  if(target.id==='vision'&&!target.probe_url)return {reachable:true,http_status:200};
  if(!target.probe_url)return {reachable:null,http_status:null};
  try{
    const response=await fetchImpl(target.probe_url,{
      method:'GET',
      headers:{'user-agent':'Quantic-Portal-Health/1.0','accept':'*/*'},
      redirect:'follow',
      signal:AbortSignal.timeout(timeoutMs)
    });
    return {reachable:response.status<500,http_status:response.status};
  }catch{
    return {reachable:false,http_status:null};
  }
}

function publicService(target,result){
  return {
    id:target.id,
    label:target.label,
    kind:target.kind,
    url:target.public_url,
    state:target.state,
    reachable:result?.reachable??null,
    http_status:result?.http_status??null
  };
}

export async function buildQuanticPortalStatus({probe=probeQuanticService}={}){
  const services=[];
  for(const target of QUANTIC_SERVICE_TARGETS){
    if(target.state==='pending'){
      services.push(publicService(target,null));
      continue;
    }
    try{
      services.push(publicService(target,await probe(target)));
    }catch{
      services.push(publicService(target,{reachable:false,http_status:null}));
    }
  }
  return {status:'ok',services};
}
