(()=>{'use strict';
document.documentElement.classList.add('qid-mail-locked');

const STYLE_ID='quantic-mail-id-gate-style';
const GATE_ID='quantic-mail-id-gate';
let backgroundObserver=null;
let shielded=[];
let previousBodyOverflow='';

function ensureStyle(){
  if(document.getElementById(STYLE_ID))return;
  const style=document.createElement('style');
  style.id=STYLE_ID;
  style.textContent=`
    #${GATE_ID}{
      position:fixed!important;
      inset:0!important;
      z-index:2147483647!important;
      width:100vw!important;
      height:100dvh!important;
      min-height:100vh!important;
      margin:0!important;
      padding:28px!important;
      display:grid!important;
      place-items:center!important;
      overflow:auto!important;
      overscroll-behavior:contain;
      background:#f3f7f9!important;
      color:#0f202b!important;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif!important;
      box-sizing:border-box!important;
      isolation:isolate;
    }
    #${GATE_ID},#${GATE_ID} *{box-sizing:border-box}
    #${GATE_ID} .qid-card{
      width:min(560px,calc(100vw - 40px))!important;
      max-width:560px!important;
      margin:auto!important;
      padding:36px!important;
      border:1px solid #e1e7ea!important;
      border-radius:26px!important;
      background:#fff!important;
      box-shadow:0 32px 90px rgba(15,32,43,.12)!important;
      color:#0f202b!important;
    }
    #${GATE_ID} .qid-kicker{margin:0 0 10px!important;color:#39869a!important;font-size:11px!important;font-weight:700!important;letter-spacing:.18em!important;text-transform:uppercase!important}
    #${GATE_ID} h1{margin:0!important;color:#0f202b!important;font-size:clamp(42px,8vw,62px)!important;line-height:.95!important;letter-spacing:-.055em!important;font-weight:560!important}
    #${GATE_ID} p{margin:18px 0 0!important;color:#6c7b84!important;line-height:1.7!important}
    #${GATE_ID} .qid-status{margin-top:24px!important;padding:15px 16px!important;border:1px solid #e1e7ea!important;border-radius:16px!important;background:#f7f9fa!important}
    #${GATE_ID} .qid-status strong{display:block!important;color:#0f202b!important;font-size:14px!important}
    #${GATE_ID} .qid-status span{display:block!important;margin-top:5px!important;color:#7d8d95!important;font-size:12px!important;line-height:1.5!important}
    #${GATE_ID} .qid-actions{display:flex!important;gap:9px!important;flex-wrap:wrap!important;margin-top:22px!important}
    #${GATE_ID} button,#${GATE_ID} a{min-height:44px!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;padding:0 16px!important;border-radius:999px!important;border:1px solid #dce5e9!important;background:#fff!important;color:#244452!important;text-decoration:none!important;font:650 13px/1 system-ui!important;cursor:pointer!important}
    #${GATE_ID} button{background:#0d1e29!important;border-color:#0d1e29!important;color:#fff!important}
    #${GATE_ID} .qid-note{font-size:11px!important;color:#92a0a7!important}
    @media(max-width:620px){
      #${GATE_ID}{padding:14px!important;place-items:center!important}
      #${GATE_ID} .qid-card{width:100%!important;padding:24px!important;border-radius:20px!important}
      #${GATE_ID} h1{font-size:42px!important}
    }
  `;
  document.head.appendChild(style);
}

function isolateNode(node){
  if(!(node instanceof HTMLElement)||node.id===GATE_ID||node.dataset?.qidGateIgnored==='true')return;
  if(shielded.some(entry=>entry.node===node))return;
  shielded.push({
    node,
    inert:node.inert,
    ariaHidden:node.getAttribute('aria-hidden')
  });
  node.inert=true;
  node.setAttribute('aria-hidden','true');
}

function shieldBackground(){
  if(!document.body)return;
  previousBodyOverflow=document.body.style.overflow;
  document.body.style.overflow='hidden';
  [...document.body.children].forEach(isolateNode);
  if(backgroundObserver)return;
  backgroundObserver=new MutationObserver(mutations=>{
    for(const mutation of mutations){
      for(const node of mutation.addedNodes){
        if(node instanceof HTMLElement&&node.id!==GATE_ID)isolateNode(node);
      }
    }
    const gate=document.getElementById(GATE_ID);
    if(!gate)ensureGate();
  });
  backgroundObserver.observe(document.body,{childList:true});
}

function restoreBackground(){
  backgroundObserver?.disconnect();
  backgroundObserver=null;
  for(const entry of shielded){
    if(!entry.node.isConnected)continue;
    entry.node.inert=entry.inert;
    if(entry.ariaHidden===null)entry.node.removeAttribute('aria-hidden');
    else entry.node.setAttribute('aria-hidden',entry.ariaHidden);
  }
  shielded=[];
  if(document.body)document.body.style.overflow=previousBodyOverflow;
}

function ensureGate(){
  const existing=document.getElementById(GATE_ID);
  if(existing)return existing;
  if(!document.body)return null;
  const gate=document.createElement('main');
  gate.id=GATE_ID;
  gate.dataset.qidGateIgnored='true';
  gate.setAttribute('role','dialog');
  gate.setAttribute('aria-modal','true');
  gate.setAttribute('aria-labelledby','qid-gate-title');
  gate.innerHTML=`<section class="qid-card" role="status" aria-live="polite">
    <p class="qid-kicker">QUANTIC MAIL · QUANTIC ID</p>
    <h1 id="qid-gate-title">Quantic ID requis.</h1>
    <p>Quantic Mail ne s’ouvre que lorsque Quantic Identity Vault est installé sur ce PC ou lancé depuis une clé USB et qu’une identité est active.</p>
    <div class="qid-status"><strong data-qid-gate-title>Vérification…</strong><span data-qid-gate-detail>Recherche de Quantic Identity Vault sur cet appareil.</span></div>
    <div class="qid-actions"><button type="button" data-qid-gate-retry>Réessayer</button><a href="/quantic/">Ouvrir Quantic ID</a><a href="/downloads/#identity-vault">Installer Identity Vault</a></div>
    <p class="qid-note">Aucun mot de passe de secours n’est proposé. La clé privée reste dans Identity Vault.</p>
  </section>`;
  document.body.prepend(gate);
  gate.querySelector('[data-qid-gate-retry]').addEventListener('click',check);
  shieldBackground();
  return gate;
}

function setStatus(title,detail){
  const gate=ensureGate();
  if(!gate)return;
  gate.querySelector('[data-qid-gate-title]').textContent=title;
  gate.querySelector('[data-qid-gate-detail]').textContent=detail;
}

function unlock(){
  restoreBackground();
  document.documentElement.classList.remove('qid-mail-locked');
  document.documentElement.dataset.quanticId='active';
  document.getElementById(GATE_ID)?.remove();
}

async function check(){
  ensureStyle();
  if(!document.body){
    document.addEventListener('DOMContentLoaded',check,{once:true});
    return;
  }
  ensureGate();
  shieldBackground();
  if(!window.QuanticID?.probe){
    setStatus('Runtime Quantic ID absent','Le portail ne peut pas vérifier Identity Vault. Quantic Mail reste verrouillé.');
    return;
  }
  setStatus('Vérification de Quantic ID…','Recherche de Quantic Identity Vault sur cet ordinateur.');
  const result=await window.QuanticID.probe();
  if(result.ok){
    unlock();
    return;
  }
  if(result.installed){
    setStatus('Identité inactive','Quantic Identity Vault est présent, mais aucune identité active n’a été détectée.');
    return;
  }
  setStatus('Quantic Identity Vault non détecté','Installez Identity Vault sur ce PC ou lancez la version portable depuis votre clé USB, puis activez Quantic ID.');
}

ensureStyle();
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',check,{once:true}):check();
})();