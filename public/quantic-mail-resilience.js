(()=>{'use strict';
const MANIFEST_TIMEOUT_MS=10000;
let timer=null;

function appIsReady(){
  return Boolean(document.querySelector('.qn-mail-app,.qm-shell,.qm-header'));
}
function getCard(){
  return document.querySelector('.qn-onboarding-card');
}
function stuckHeading(){
  const h=getCard()?.querySelector('h1');
  const value=String(h?.textContent||'');
  return /Préparation de Quantic Mail|Vérification du manifeste/i.test(value);
}
function addRecovery(card){
  if(card.querySelector('[data-qm-recovery]'))return;
  const actions=document.createElement('div');
  actions.className='qn-recovery-actions';
  actions.dataset.qmRecovery='true';
  actions.innerHTML='<button type="button">Réessayer</button><a href="/network/">État du réseau</a>';
  actions.querySelector('button').addEventListener('click',()=>location.reload());
  card.appendChild(actions);
}
function showRecovery(){
  if(appIsReady())return;
  const card=getCard();
  if(!card||!stuckHeading())return;
  const h=card.querySelector('h1');
  const note=card.querySelector('.qn-footnote');
  if(h)h.textContent='Vérification plus longue que prévu';
  if(note)note.textContent='Quantic Mail n’a pas terminé sa préparation. Vous pouvez réessayer maintenant ou vérifier l’état du réseau.';
  addRecovery(card);
}
function schedule(){
  clearTimeout(timer);
  timer=setTimeout(showRecovery,MANIFEST_TIMEOUT_MS);
}
const observer=new MutationObserver(()=>{
  if(appIsReady()){
    clearTimeout(timer);
    observer.disconnect();
    return;
  }
  if(stuckHeading())schedule();
});
function boot(){
  schedule();
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
}
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',boot,{once:true}):boot();
})();