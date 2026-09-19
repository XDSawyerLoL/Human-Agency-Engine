(()=>{'use strict';
const VISION_TIMEOUT_MS=12000;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const pct=value=>Math.max(0,Math.min(100,Number(value)||0));
const horizon=value=>({immediate:'≤ 72 h',near:'≤ 1 mois',medium:'≤ 3 mois',long:'≤ 1 an',deep:'> 1 an'}[value]||String(value||'Horizon'));
function set(id,value){const el=document.getElementById(id);if(el)el.textContent=value}
function scenarioCard(f){
  const p=pct(f?.probability?.percent);
  const title=f?.title||f?.question||f?.scenario||'Scénario surveillé';
  const domain=String(f?.domain||'signal').replaceAll('_',' ');
  const direction=f?.probability_direction||'stable';
  const detail=f?.summary||f?.rationale||f?.forecast_summary||'Probabilité recalculée à partir des signaux observés.';
  return `<article class="qv8-scenario">
    <div class="qv8-scenario-meta"><span>${esc(domain)}</span><span>${esc(horizon(f?.horizon_tier))}</span></div>
    <h4>${esc(title)}</h4>
    <p>${esc(String(detail).slice(0,180))}</p>
    <div class="qv8-prob"><div class="qv8-prob-row"><strong>${Math.round(p)}%</strong><span>${esc(direction)}</span></div><div class="qv8-bar"><i style="width:${p}%"></i></div></div>
  </article>`;
}
function pulseCard(f){
  const delta=Number(f?.probability_delta_points||0);
  const title=f?.title||f?.question||'Signal en évolution';
  const label=delta>1?'Hausse':delta<-1?'Baisse':'Stable';
  return `<article class="qv8-pulse-card"><small>${esc(label)} · ${esc(String(f?.domain||'signal').replaceAll('_',' '))}</small><h3>${esc(title)}</h3><p>${delta?('Variation récente : '+(delta>0?'+':'')+delta.toFixed(1)+' points.'):'Trajectoire surveillée par Providence.'}</p></article>`;
}
async function fetchSnapshot(){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),VISION_TIMEOUT_MS);
  try{return await fetch('/api/snapshot',{credentials:'same-origin',cache:'no-store',signal:controller.signal});}
  finally{clearTimeout(timer);}
}
function renderLoadError(){
  const scenarios=document.getElementById('qv8Scenarios');
  const pulse=document.getElementById('qv8Pulse');
  if(scenarios)scenarios.innerHTML='<div class="qv8-empty">Providence n’a pas répondu dans le délai prévu.<br><button type="button" class="qv8-retry" data-qv8-retry>Réessayer</button></div>';
  if(pulse)pulse.innerHTML='<div class="qv8-empty">Les variations seront affichées dès que le moteur répondra.</div>';
  document.querySelector('[data-qv8-retry]')?.addEventListener('click',()=>load());
}
async function load(){
  try{
    const response=await fetchSnapshot();
    if(response.status===401){location.replace('/quantic/?next='+encodeURIComponent(location.pathname));return}
    if(!response.ok)throw new Error('snapshot_unavailable');
    const data=await response.json();
    const forecasts=Array.isArray(data.forecasts)?data.forecasts:[];
    const summary=data.summary||{};
    set('qv8ForecastCount',forecasts.length||summary.predictions_returned||0);
    set('qv8SignalCount',summary.signals_considered||0);
    set('qv8SourceCount',summary.source_providers||0);
    set('qv8Updated',data.generated_at?new Date(data.generated_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):'—');
    const ranked=[...forecasts].sort((a,b)=>(Number(b?.probability?.percent)||0)-(Number(a?.probability?.percent)||0)).slice(0,3);
    const scenarios=document.getElementById('qv8Scenarios');
    if(scenarios)scenarios.innerHTML=ranked.length?ranked.map(scenarioCard).join(''):'<div class="qv8-empty">Aucun scénario disponible pour le moment.</div>';
    const changing=[...forecasts].sort((a,b)=>Math.abs(Number(b?.probability_delta_points)||0)-Math.abs(Number(a?.probability_delta_points)||0)).slice(0,3);
    const pulse=document.getElementById('qv8Pulse');
    if(pulse)pulse.innerHTML=changing.length?changing.map(pulseCard).join(''):'<div class="qv8-empty">Les variations apparaîtront ici après les prochaines recalibrations.</div>';
  }catch{
    renderLoadError();
  }
}
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',load,{once:true}):load();
})();