(()=>{'use strict';
const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const DOMAIN={natural_hazards:'Risques naturels',weather_climate:'Climat',cyber_technology:'Technologie',public_health:'Santé',financial_stress:'Finance',energy:'Énergie',economy_labor:'Économie',supply_fuel:'Logistique',social_collective_behavior:'Société',geopolitics_security:'Géopolitique',regulation_policy:'Régulation',transport_mobility:'Transport'};
const title=f=>f?.title||f?.headline||f?.outcome||'Scénario';
const prob=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return Math.round(p);const e=Number(f?.probability?.estimate);return Number.isFinite(e)?Math.round(e*100):0};
const conf=f=>Math.round(Number(f?.consolidation?.score??f?.confidence??0)||0);
const active=s=>(s?.forecasts||[]).filter(f=>!['resolved','invalidated'].includes(f?.status));
const score=f=>prob(f)+conf(f)*.22+(Number(f?.probability_delta_points)||0)*1.5;
const json=async u=>{try{const r=await fetch(u,{cache:'no-store'});return r.ok?await r.json():null}catch{return null}};
function metric(id,value,sub){const n=$(id);if(!n)return;n.querySelector('strong').textContent=value??'—';if(sub)n.querySelector('span').textContent=sub}
const REGIONS=[
 [/(états?-unis|usa|united states|californ|texas|new york|amérique du nord|north america)/i,120,112],
 [/(canada)/i,118,73],[/(mexique|mexico|amérique centrale|central america)/i,132,145],[/(brésil|brazil|amérique du sud|south america)/i,192,202],
 [/(europe occidentale|europe de l'ouest|western europe|france|allemagne|germany|royaume-uni|uk|italie|italy|espagne|spain)/i,302,90],
 [/(europe|union européenne|eu)/i,323,95],[/(afrique|africa|sahel)/i,315,165],[/(moyen-orient|middle east|israël|iran|golfe)/i,377,128],
 [/(inde|india|asie du sud|south asia|népal|nepal)/i,432,145],[/(chine|china|asie orientale|east asia|taïwan|taiwan)/i,486,107],
 [/(japon|japan|corée|korea)/i,527,106],[/(asie|asia|asie-pacifique|asia-pacific)/i,470,120],[/(australie|australia|océanie|oceania)/i,525,205],
 [/(monde|global|world)/i,330,120]
];
function regionPoint(region){for(const [re,x,y] of REGIONS)if(re.test(String(region||'')))return{x,y};return null}
function mapSvg(rows){
 const grouped=new Map();for(const f of rows){const p=regionPoint(f.region||f.geography);if(!p)continue;const key=`${p.x}:${p.y}`,old=grouped.get(key)||{...p,max:0,n:0};old.max=Math.max(old.max,prob(f));old.n+=1;grouped.set(key,old)}
 const marks=[...grouped.values()].sort((a,b)=>b.max-a.max||b.n-a.n).slice(0,9).map(m=>{const color=m.max>=65?'#ff5b57':m.max>=50?'#ffc443':'#39dd91',r=Math.min(18,8+m.n*2);return `<g><circle cx="${m.x}" cy="${m.y}" r="${r+10}" fill="${color}" opacity=".08"/><circle cx="${m.x}" cy="${m.y}" r="${r}" fill="${color}" opacity=".22"/><circle cx="${m.x}" cy="${m.y}" r="4" fill="${color}"/><circle cx="${m.x}" cy="${m.y}" r="${r+5}" fill="none" stroke="${color}" opacity=".45"/></g>`}).join('');
 return `<svg viewBox="0 0 620 275" role="img" aria-label="Carte des zones chaudes dérivée des prévisions actives"><path fill="#073a69" stroke="#128ff2" stroke-width="1" d="M52 93l36-34 49-8 37 19 21 36-13 25-41 7-18 23-35-12-16-25-28-8zm157-28 23-26 53-16 54 9 32 22 12 32-25 22-45-5-30 22-38-9-21-28zm190 37 25-19 48 3 34 22 5 29-19 19-40 4-17 25-30-5-8-25-24-14zm-9-77 25-14 32 6 10 18-21 13-31-3zm119 139 25-7 30 12 13 22-20 18-37-5-14-20zM289 151l18 13 9 27-13 31-22 20-17-29 6-34zM154 158l20 22-2 33-19 29-17-23 4-34z"/>${marks}</svg>`}
function render(rows,snapshot,track){
 const summary=snapshot?.summary||{};const resolved=Number(track?.resolution?.resolved??track?.resolution?.total_resolved??track?.resolved_scenarios??track?.tracked_scenarios??0)||0;
 const eceRaw=Number(track?.calibration?.global?.ece??track?.calibration?.ece??track?.ece??track?.scores?.ece);const cal=Number.isFinite(eceRaw)?Math.max(0,Math.min(100,Math.round((1-(eceRaw<=1?eceRaw:eceRaw/100))*1000)/10)):null;
 const avgConf=rows.length?Math.round(rows.reduce((a,f)=>a+conf(f),0)/rows.length):0;
 metric('#mSignals',summary.signals_considered??summary.signal_count??snapshot?.signals?.length??'—','observés maintenant');metric('#mForecasts',rows.length,'scénarios publiés');metric('#mResolved',resolved||'—','registre vérifiable');metric('#mCalibration',cal!==null?`${cal}%`:'—','100 − ECE');metric('#mConfidence',avgConf?`${avgConf}%`:'—','solidité moyenne');
 const top=[...rows].sort((a,b)=>score(b)-score(a)).slice(0,5);$('#overviewPriorities').innerHTML=top.map(f=>`<div class="pv14-priority-row"><span class="prio ${prob(f)>=65?'high':prob(f)>=50?'mid':'low'}">${prob(f)>=65?'ÉLEVÉE':prob(f)>=50?'MOYENNE':'FAIBLE'}</span><div><b>${esc(title(f))}</b><small>${esc(f.region||'Monde')} · ${esc(DOMAIN[f.domain]||f.domain||'')}</small></div><strong>${prob(f)}%</strong><em>${conf(f)||'—'}%</em></div>`).join('')||'<div class="sports-empty">Aucune prévision active.</div>';
 const dm=new Map();for(const f of rows){const k=f.domain||'other';dm.set(k,(dm.get(k)||0)+1)}const domains=[...dm.entries()].sort((a,b)=>b[1]-a[1]).slice(0,7);$('#overviewDomains').innerHTML=domains.map(([k,n],i)=>`<article class="pv14-domain d${i}"><span>${['◔','▥','◉','ϟ','♡','▣','⚑'][i%7]}</span><div><b>${esc(DOMAIN[k]||k)}</b><strong>${n}</strong><small>prévision${n>1?'s':''} active${n>1?'s':''}</small></div></article>`).join('');
 const decision=top.slice(0,4);$('#overviewDecision').innerHTML=decision.map(f=>`<div class="pv14-action"><span>${prob(f)>=65?'!':'↗'}</span><div><b>${esc((f.watch_next||f.favorable_signals||[])[0]||title(f))}</b><small>${esc(title(f))}</small></div><em class="${prob(f)>=65?'high':prob(f)>=50?'mid':'low'}">${prob(f)>=65?'ÉLEVÉE':prob(f)>=50?'MOYENNE':'FAIBLE'}</em></div>`).join('');
 const alerts=[...rows].filter(f=>f.probability_direction==='rising'||Number(f.probability_delta_points)>0||prob(f)>=65).sort((a,b)=>(Number(b.probability_delta_points)||0)-(Number(a.probability_delta_points)||0)||prob(b)-prob(a)).slice(0,5);$('#overviewAlerts').innerHTML=alerts.map((f,i)=>`<div class="pv14-alert"><span class="dot c${i}">${i<2?'△':i<4?'!':'✓'}</span><div><b>${esc(title(f))}</b><small>${esc(f.region||'Monde')} · ${esc(DOMAIN[f.domain]||f.domain||'')}</small></div><em>${Number(f.probability_delta_points)>0?`+${Number(f.probability_delta_points)} pts`:prob(f)+'%'}</em></div>`).join('')||'<div class="sports-empty">Aucune alerte forte.</div>';
 const avgs=[...dm.keys()].slice(0,6).map(k=>{const list=rows.filter(f=>f.domain===k);return {k,v:list.length?Math.round(list.reduce((a,f)=>a+prob(f),0)/list.length):0}});$('#overviewTrend').innerHTML=`<div class="pv14-trend-bars">${avgs.map((x,i)=>`<div><label>${esc(DOMAIN[x.k]||x.k)}</label><span><i style="width:${x.v}%;--c:${['#1694ff','#ff5b62','#a35cff','#43e889','#ffc64a','#20d9ff'][i%6]}"></i></span><b>${x.v}</b></div>`).join('')}</div>`;
 $('#overviewMap').innerHTML=mapSvg(rows)+`<div class="pv14-map-foot"><span><b>${summary.signals_considered??'—'}</b> signaux</span><span><b>${summary.source_providers??summary.sources_contributing??'—'}</b> sources</span><span><b>${domains.length}</b> domaines majeurs</span></div>`;
}
async function run(){const [snapshot,track]=await Promise.all([json('/api/snapshot'),json('/api/track-record')]);if(snapshot)render(active(snapshot),snapshot,track||{})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run,{once:true});else run();
})();