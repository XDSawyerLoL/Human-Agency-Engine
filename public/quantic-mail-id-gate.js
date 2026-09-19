(()=>{'use strict';
document.documentElement.classList.add('qid-mail-locked');

const STYLE_ID='quantic-mail-id-gate-style';
const GATE_ID='quantic-mail-id-gate';

function ensureStyle(){
  if(document.getElementById(STYLE_ID))return;
  const style=document.createElement('style');
  style.id=STYLE_ID;
  style.textContent=`
    html.qid-mail-locked body>*:not(#${GATE_ID}){display:none!important}
    #${GATE_ID}{min-height:100vh;display:grid;place-items:center;padding:28px;background:linear-gradient(180deg,#fafcfd,#eef3f6);color:#0f202b;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}
    #${GATE_ID} .qid-card{width:min(560px,100%);padding:36px;border:1px solid #e1e7ea;border-radius:26px;background:#fff;box-shadow:0 32px 90px rgba(15,32,43,.12)}
    #${GATE_ID} .qid-kicker{margin:0 0 10px;color:#39869a;font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase}
    #${GATE_ID} h1{margin:0;color:#0f202b;font-size:clamp(42px,8vw,62px);line-height:.95;letter-spacing:-.055em;font-weight:560}
    #${GATE_ID} p{margin:18px 0 0;color:#6c7b84;line-height:1.7}
    #${GATE_ID} .qid-status{margin-top:24px;padding:15px 16px;border:1px solid #e1e7ea;border-radius:16px;background:#f7f9fa}
    #${GATE_ID} .qid-status strong{display:block;font-size:14px}
    #${GATE_ID} .qid-status span{display:block;margin-top:5px;color:#7d8d95;font-size:12px;line-height:1.5}
    #${GATE_ID} .qid-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:22px}
    #${GATE_ID} button,#${GATE_ID} a{min-height:44px;display:inline-flex;align-items:center;justify-content:center;padding:0 16px;border-radius:999px;border:1px solid #dce5e9;background:#fff;color:#244452;text-decoration:none;font:650 13px/1 system-ui;cursor:pointer}
    #${GATE_ID} button{background:#0d1e29;border-color:#0d1e29;color:#fff}
    #${GATE_ID} .qid-note{font-size:11px;color:#92a0a7}
  `;
  document.head.appendChild(style);
}

function ensureGate(){
  if(document.getElementById(GATE_ID))return document.getElementById(GATE_ID);
  const gate=document.createElement('main');
  gate.id=GATE_ID;
  gate.innerHTML=`<section class="qid-card" role="status" aria-live="polite">
    <p class="qid-kicker">QUANTIC MAIL · QUANTIC ID</p>
    <h1>Quantic ID requis.</h1>
    <p>Quantic Mail ne s’ouvre que lorsque le logiciel Quantic ID est installé sur ce PC et qu’une identité est active.</p>
    <div class="qid-status"><strong data-qid-gate-title>Vérification…</strong><span data-qid-gate-detail>Recherche du logiciel Quantic ID sur cet appareil.</span></div>
    <div class="qid-actions"><button type="button" data-qid-gate-retry>Réessayer</button><a href="/quantic/">Ouvrir Quantic ID</a></div>
    <p class="qid-note">Aucun mot de passe de secours n’est proposé. Le portail vérifie uniquement le compagnon local Quantic ID.</p>
  </section>`;
  document.body.prepend(gate);
  gate.querySelector('[data-qid-gate-retry]').addEventListener('click',check);
  return gate;
}

function setStatus(title,detail){
  const gate=ensureGate();
  gate.querySelector('[data-qid-gate-title]').textContent=title;
  gate.querySelector('[data-qid-gate-detail]').textContent=detail;
}

function unlock(){
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
  if(!window.QuanticID?.probe){
    setStatus('Runtime Quantic ID absent','Le portail ne peut pas vérifier l’identité locale. Quantic Mail reste verrouillé.');
    return;
  }
  setStatus('Vérification de Quantic ID…','Recherche du logiciel d’identité sur cet ordinateur.');
  const result=await window.QuanticID.probe();
  if(result.ok){
    unlock();
    return;
  }
  if(result.installed){
    setStatus('Identité inactive','Le logiciel Quantic ID est présent, mais aucune identité active n’a été détectée.');
    return;
  }
  setStatus('Application Quantic ID non détectée','Installez puis activez le logiciel Quantic ID sur ce PC avant d’utiliser Quantic Mail.');
}

ensureStyle();
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',check,{once:true}):check();
})();