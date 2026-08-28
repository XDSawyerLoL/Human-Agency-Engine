(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const p=f=>Math.round(Number(f?.probability?.percent ?? (Number(f?.probability?.estimate)||0)*100)||0);
const conf=f=>Math.round(Number(f?.consolidation?.score??f?.confidence??0)||0);
const title=f=>f?.title||f?.headline||f?.outcome||'Scénario';
const summary=f=>f?.summary||f?.public_summary||f?.what_we_know||f?.why_now||'';
const active=f=>!['resolved','invalidated'].includes(f?.status);
function score(f){return p(f)+conf(f)*.25+Math.abs(Number(f?.probability_delta_points)||0)*1.5+Number(f?.signal_convergence?.probability_delta_points||0)*2}
function horizon(f){const map={immediate:'≤ 72 h',near:'Jours à semaines',medium:'Mois',long:'1–3 ans',strategic:'3–5 ans',deep:'5 ans +'};return map[f?.horizon_tier]||f?.horizon_tier||'Horizon variable'}
async function run(){
 const box=document.querySelector('#futureFocusMain');if(!box)return;
 try{const r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);const d=await r.json();const rows=(d.forecasts||[]).filter(active).sort((a,b)=>score(b)-score(a));const f=rows[0];if(!f){box.innerHTML='<span class="future-focus-label">PRÉVISION PRIORITAIRE</span><div class="v4-empty">Aucun scénario actif.</div>';return}
 const c=f.signal_convergence||{},strong=Number(c.strong_signals?.length||0),weak=Number(c.weak_signals?.length||0),delta=Number(c.probability_delta_points||0),up=(f.favorable_signals||f.probability_up_if||[])[0],down=(f.contrary_signals||f.probability_down_if||[])[0];
 box.innerHTML=`<span class="future-focus-label">PRÉVISION PRIORITAIRE · ${esc(f.domain||'monde')}</span><div class="future-focus-row"><div class="future-focus-prob">${p(f)}<small>%</small></div><div><h2>${esc(title(f))}</h2><p>${esc(summary(f))}</p><div class="future-focus-meta"><span>${esc(f.region||'Monde')}</span><span>${esc(horizon(f))}</span><span>preuves ${conf(f)||'—'}/100</span><span>${strong} forts · ${weak} faibles · Δ ${delta>0?'+':''}${delta} pt${Math.abs(delta)>1?'s':''}</span></div></div></div><div class="future-focus-reasons"><div><small>CE QUI RENFORCE</small><b>${esc(up||c.explanation||'Convergence indépendante des sources et mécanismes compatibles.')}</b></div><div><small>CE QUI FRAGILISE</small><b>${esc(down||'Absence de nouveaux précurseurs ou normalisation des signaux observés.')}</b></div></div>`;
 }catch(e){box.innerHTML=`<span class="future-focus-label">PRÉVISION PRIORITAIRE</span><div class="v4-empty">Champ prédictif indisponible : ${esc(e.message)}</div>`}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run,{once:true});else run();
})();