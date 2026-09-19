(()=>{'use strict';
function text(selector,value){
  const node=document.querySelector(selector);
  if(node)node.textContent=value;
}
function setState(state,title,detail){
  const card=document.querySelector('[data-quantic-id-state]');
  if(card)card.dataset.state=state;
  text('[data-quantic-id-title]',title);
  text('[data-quantic-id-detail]',detail);
}
function setApps(enabled){
  document.querySelectorAll('[data-quantic-id-app]').forEach(link=>{
    if(['mail','vision'].includes(link.dataset.quanticIdApp)){
      link.setAttribute('aria-disabled',enabled?'false':'true');
      link.classList.toggle('is-locked',!enabled);
    }
  });
}
function safeNext(){
  const value=new URLSearchParams(location.search).get('next')||'';
  if(!value.startsWith('/')||value.startsWith('//'))return'';
  return value;
}
async function currentSession(){
  try{
    const response=await fetch('/api/id/session',{cache:'no-store',credentials:'same-origin'});
    return response.ok?response.json():null;
  }catch{return null}
}
async function establishServerSession(){
  const challengeResponse=await fetch('/api/id/challenge',{
    method:'POST',
    credentials:'same-origin',
    headers:{'Content-Type':'application/json'},
    body:'{}'
  });
  if(!challengeResponse.ok)throw new Error('identity_challenge_failed');
  const challenge=await challengeResponse.json();
  if(!window.QuanticID?.assert)throw new Error('identity_assertion_unavailable');
  const proof=await window.QuanticID.assert({challenge:challenge.challenge,audience:challenge.audience});
  const sessionResponse=await fetch('/api/id/session',{
    method:'POST',
    credentials:'same-origin',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({proof})
  });
  const session=await sessionResponse.json().catch(()=>({}));
  if(!sessionResponse.ok||!session.authenticated)throw new Error(session.error||'identity_session_failed');
  return session;
}
async function check(){
  setState('checking','Recherche de Quantic ID…','Vérification d’Identity Vault et de la session Sillage.');
  setApps(false);

  const existing=await currentSession();
  if(existing?.authenticated){
    setState('ready','Quantic ID actif','Session Sillage sécurisée · '+existing.keyId);
    setApps(true);
    const next=safeNext();
    if(next)setTimeout(()=>location.replace(next),250);
    return;
  }

  if(!window.QuanticID?.probe){
    setState('missing','Runtime Quantic ID indisponible','Le composant local d’identité n’est pas disponible.');
    return;
  }
  const result=await window.QuanticID.probe();
  if(!result.ok){
    if(result.installed){
      setState('inactive','Identity Vault détecté, identité inactive','Ouvrez Quantic Identity Vault et activez votre identité, puis relancez la détection.');
    }else{
      setState('missing','Quantic Identity Vault non détecté','Installez Identity Vault sur ce PC ou lancez la version portable depuis une clé USB.');
    }
    return;
  }

  setState('checking','Identity Vault actif','Signature du challenge Sillage en cours…');
  try{
    const session=await establishServerSession();
    setState('ready','Quantic ID actif','Session Sillage sécurisée · '+(result.label||session.keyId));
    setApps(true);
    const next=safeNext();
    if(next)setTimeout(()=>location.replace(next),250);
  }catch(error){
    setState('missing','Session Quantic ID refusée','Identity Vault est actif, mais la preuve n’a pas pu être validée par Sillage.');
  }
}
document.addEventListener('click',event=>{
  const retry=event.target.closest('[data-quantic-id-retry]');
  if(retry){event.preventDefault();check();}
  const app=event.target.closest('[data-quantic-id-app]');
  if(app&&app.classList.contains('is-locked')){event.preventDefault();check();}
});
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',check,{once:true}):check();
})();