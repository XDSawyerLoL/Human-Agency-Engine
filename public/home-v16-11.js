(()=>{'use strict';
const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const DOMAIN={natural_hazards:'Risques naturels',weather_climate:'Climat',cyber_technology:'Technologie',public_health:'Santé',financial_stress:'Finance',energy:'Énergie',economy_labor:'Économie',supply_fuel:'Logistique',social_collective_behavior:'Société',geopolitics_security:'Géopolitique',regulation_policy:'Régulation',transport_mobility:'Transport'};
const colors=['#ffc85a','#a777ff','#4f8dff'];
const title=f=>f?.title||f?.headline||f?.outcome||'Scénario';
const prob=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return Math.max(0,Math.min(100,Math.round(p)));const e=Number(f?.probability?.estimate);return Number.isFinite(e)?Math.max(0,Math.min(100,Math.round(e*100))):0};
const conf=f=>Math.max(0,Math.min(100,Math.round(Number(f?.consolidation?.score??f?.confidence??0)||0)));
const active=f=>!['resolved','invalidated','expired'].includes(String(f?.status||'').toLowerCase());
const score=f=>prob(f)+conf(f)*.22+(Number(f?.probability_delta_points)||0)*1.5;
const clip=(v,n=86)=>{v=String(v||'').trim();return v.length>n?v.slice(0,n-1)+'…':v};
async function get(u){try{const r=await fetch(u,{cache:'no-store'});return r.ok?await r.json():null}catch{return null}}
function card(f,i){const horizon=f?.horizon_label||f?.horizon_tier||'Horizon actif';const region=f?.region||f?.geography||'Monde';return `<article class="p15-forecast-card" style="--ring:${colors[i]};--branch-color:${colors[i]}"><small>${esc(DOMAIN[f?.domain]||f?.domain||'PRÉVISION')}</small><h3>${esc(clip(title(f),100))}</h3><p>${esc(region)} · ${esc(horizon)}</p><div class="p15-prob-ring" style="--p:${prob(f)};--ring:${colors[i]}"><b>${prob(f)}%</b></div><div class="p15-mini-meta"><span>Solidité ${conf(f)||'—'}/100</span><span>${Number(f?.probability_delta_points)>0?`+${Number(f.probability_delta_points)} pts`:'stable'}</span></div></article>`}
async function boot(){const [snapshot,track]=await Promise.all([get('/api/snapshot'),get('/api/track-record')]);const rows=(snapshot?.forecasts||[]).filter(active).sort((a,b)=>score(b)-score(a)).slice(0,3);const host=$('#p15ForecastCards');if(host)host.innerHTML=rows.length?rows.map(card).join(''):'<div class="p1611-empty">Providence observe les signaux. Aucun futur prioritaire n’est publié pour le moment.</div>';
 const forecastCount=$('#p1611ForecastCount');if(forecastCount)forecastCount.textContent=String((snapshot?.forecasts||[]).filter(active).length||0);
 const signalCount=$('#p1611SignalCount');if(signalCount)signalCount.textContent=String(snapshot?.summary?.signals_considered??snapshot?.summary?.signal_count??snapshot?.signals?.length??'—');
 const cal=$('#p1611Calibration');if(cal){const raw=Number(track?.calibration?.global?.ece??track?.calibration?.ece??track?.ece);cal.textContent=Number.isFinite(raw)?`${Math.max(0,Math.min(100,Math.round((1-(raw<=1?raw:raw/100))*100)))}%`:'en collecte';}
 const updateDock=()=>document.body.classList.toggle('p1611-dock-visible',window.scrollY>Math.min(420,window.innerHeight*.48));updateDock();window.addEventListener('scroll',updateDock,{passive:true});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();