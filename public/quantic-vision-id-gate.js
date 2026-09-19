(()=>{'use strict';
document.documentElement.classList.add('qid-vision-locked');

const GATE_ID='quantic-vision-id-gate';
const STYLE_ID='quantic-vision-id-gate-style';
let observer=null;
let shielded=[];
let previousOverflow='';

function ensureStyle(){
  if(document.getElementById(STYLE_ID))return;
  const style=document.createElement('style');
  style.id=STYLE_ID;
  style.textContent=`
    html.qid-vision-locked{background:#f3f7f9!important}
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
      overscroll-behavior:contain!important;
      background:
        radial-gradient(720px 440px at 82% -8%,rgba(19,184,210,.09),transparent 70%),
        linear-gradient(180deg,#fbfcfd,#eef3f6)!important;
      color:#0f202b!important;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif!important;
      box-sizing:border-box!important;
      isolation:isolate!important;
    }
    #${GATE_ID},#${GATE_ID} *{box-sizing:border-box!important}
    #${GATE_ID} .qidv-card{
      width:min(620px,calc(100vw - 40px))!important;
      padding:38px!important;
      border:1px solid #e1e7ea!important;
      border-radius:28px!important;
      background:#fff!important;
      box-shadow:0 38px 100px rgba(15,32,43,.13)!important;
    }
    #${GATE_ID} .qidv-kicker{margin:0 0 12px!important;color:#39869a!important;font-size:11px!important;font-weight:750!important;letter-spacing:.18em!important;text-transform:uppercase!important}
    #${GATE_ID} h1{margin:0!important;color:#0f202b!important;font-size:clamp(42px,8vw,64px)!important;line-height:.95!important;letter-spacing:-.055em!important;font-weight:560!important}
    #${GATE_ID} p{margin:18px 0 0!important;color:#6c7b84!important;line-height:1.72!important}
    #${GATE_ID} .qidv-status{margin-top:24px!important;padding:15px 16px!important;border:1px solid #e1e7ea!important;border-radius:16px!important;background:#f7f9fa!important}
    #${GATE_ID} .qidv-status strong{display:block!important;color:#0f202b!important;font-size:14px!important}
    #${GATE_ID} .qidv-status span{display:block!important;margin-top:5px!important;color:#7d8d95!important;font-size:12px!important;line-height:1.5!important}
    #${GATE_ID} .qidv-actions{display:flex!important;gap:9px!important;flex-wrap:wrap!important;margin-top:22px!important}
    #${GATE_ID} button,#${GATE_ID} a{min-height:44px!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;padding:0 16px!important;border-radius:999px!important;border:1px solid #dce5e9!important;background:#fff!important;color:#244452!important;text-decoration:none!important;font:650 13px/1 system-ui!important;cursor:pointer!important}
    #${GATE_ID} button{background:#0d1e29!important;border-color:#0d1e29!important;color:#fff!important}
    #${GATE_ID} .qidv-note{font-size:11px!important;color:#92a0a7!important}
    @media(max-width:620px){
      #${GATE_ID}{padding:14px!important}
      #${GATE_ID} .qidv-card{width:100%!important;padding:24px!important;border-radius:20px!important}
      #${GATE_ID} h1{font-size:42px!important}
    }
  `;
  document.head.appendChild(style);
}

function isolateNode(node){
  if(!(node instanceof HTMLElement)||node.id===GATE_ID||node.dataset?.qidVisionGate==='true')return;
  if(shielded.some(entry=>entry.node===node))return;
  shielded.push({node,inert:node.inert,ariaHidden:node.getAttribute('aria-hidden')});
  node.inert=true;
  node.setAttribute('aria-hidden','true');
}

function shield(){
  if(!document.body)return;
  previousOverflow=document.body.style.overflow;
  document.body.style.overflow='hidden';
  [...document.body.children].forEach(isolateNode);
  if(observer)return;
  observer=new MutationObserver(mutations=>{
    for(const mutation of mutations){
      for(const node of mutation.addedNodes){
        if(node instanceof HTMLElement&&node.id!==GATE_ID)isolateNode(node);
      }
    }
    if(!document.getElementById(GATE_ID))ensureGate();
  });
  observer.observe(document.body,{childList:true});
}

function restore(){
  observer?.disconnect();
  observer=null;
  for(const entry of shielded){
    if(!entry.node.isConnected)continue;
    entry.node.inert=entry.inert;
    if(entry.ariaHidden===null)entry.node.removeAttribute('aria-hidden');
    else entry.node.setAttribute('aria-hidden',entry.ariaHidden);
  }
  shielded=[];
  if(document.body)document.body.style.overflow=previousOverflow;
}

function ensureGate(){
  const existing=document.getElementById(GATE_ID);
  if(existing)return existing;
  if(!document.body)return null;
  const gate=document.createElement('main');
  gate.id=GATE_ID;
  gate.dataset.qidVisionGate='true';
  gate.setAttribute('role','dialog');
  gate.setAttribute('aria-modal','true');
  gate.setAttribute('aria-labelledby','qidv-title');
  gate.innerHTML=`<section class="qidv-card" role="status" aria-live="polite">
    <p class="qidv-kicker">QUANTIC VISION · QUANTIC ID</p>
    <h1 id="qidv-title">Quantic Vision verrouillé.</h1>
    <p>Vision et les surfaces Providence ne s’ouvrent que lorsque Quantic Identity Vault est actif sur ce PC ou depuis votre clé USB.</p>
    <div class="qidv-status"><strong data-qidv-title>Vérification…</strong><span data-qidv-detail>Recherche de Quantic Identity Vault sur cet appareil.</span></div>
    <div class="qidv-actions"><button type="button" data-qidv-retry>Réessayer</button><a href="/quantic/">Ouvrir Quantic ID</a><a href="/downloads/#identity-vault">Installer Identity Vault</a></div>
    <p class="qidv-note">Aucun mot de passe de secours. Providence reste le moteur de Quantic Vision ; l’accès passe par Quantic ID.</p>
  </section>`;
  document.body.prepend(gate);
  gate.querySelector('[data-qidv-retry]').addEventListener('click',check);
  shield();
  return gate;
}

function setStatus(title,detail){
  const gate=ensureGate();
  if(!gate)return;
  gate.querySelector('[data-qidv-title]').textContent=title;
  gate.querySelector('[data-qidv-detail]').textContent=detail;
}

function unlock(){
  restore();
  document.documentElement.classList.remove('qid-vision-locked');
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
  shield();
  if(!window.QuanticID?.probe){
    setStatus('Runtime Quantic ID absent','Vision ne peut pas vérifier Identity Vault. L’accès reste verrouillé.');
    return;
  }
  setStatus('Vérification de Quantic ID…','Recherche de Quantic Identity Vault sur cet ordinateur.');
  const result=await window.QuanticID.probe();
  if(result.ok){unlock();return;}
  if(result.installed){
    setStatus('Identité inactive','Identity Vault est présent, mais aucune identité active n’a été détectée.');
    return;
  }
  setStatus('Quantic Identity Vault non détecté','Installez Identity Vault sur ce PC ou lancez la version portable depuis une clé USB, puis activez Quantic ID.');
}

ensureStyle();
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',check,{once:true}):check();
})();