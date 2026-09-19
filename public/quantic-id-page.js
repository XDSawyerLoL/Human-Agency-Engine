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
    if(link.dataset.quanticIdApp==='mail'){
      link.setAttribute('aria-disabled',enabled?'false':'true');
      link.classList.toggle('is-locked',!enabled);
    }
  });
}
async function check(){
  setState('checking','Recherche de Quantic ID…','Vérification du logiciel d’identité sur cet ordinateur.');
  setApps(false);
  if(!window.QuanticID?.probe){
    setState('missing','Runtime Quantic ID indisponible','Rechargez la page. Si le problème persiste, le composant d’identité du portail est absent.');
    return;
  }
  const result=await window.QuanticID.probe();
  if(result.ok){
    setState('ready','Quantic ID actif',result.label+' · identité détectée sur cet appareil.');
    setApps(true);
    return;
  }
  if(result.installed){
    setState('inactive','Quantic ID détecté, identité inactive','Ouvrez l’application Quantic ID et activez votre identité, puis relancez la détection.');
    return;
  }
  setState('missing','Application Quantic ID non détectée','Quantic Mail restera verrouillé tant que le logiciel Quantic ID ne sera pas installé et actif sur ce PC.');
}
document.addEventListener('click',event=>{
  const retry=event.target.closest('[data-quantic-id-retry]');
  if(retry){event.preventDefault();check();}
  const app=event.target.closest('[data-quantic-id-app="mail"]');
  if(app&&app.classList.contains('is-locked')){event.preventDefault();check();}
});
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',check,{once:true}):check();
})();