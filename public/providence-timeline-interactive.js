(()=>{'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const title=f=>f?.title||f?.headline||f?.outcome||'Scénario';
const prob=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return Math.round(p);const e=Number(f?.probability?.estimate);return Number.isFinite(e)?Math.round(e*100):0};
const conf=f=>Math.round(Number(f?.consolidation?.score??f?.confidence??0)||0);
const active=f=>!['resolved','invalidated'].includes(String(f?.status||'').toLowerCase());
const score=f=>prob(f)+conf(f)*.22+(Number(f?.probability_delta_points)||0)*1.5;
const clip=(v,n=120)=>{v=String(v||'').trim();return v.length>n?v.slice(0,n-1)+'…':v};
const colors=['#ffc85a','#a777ff','#4f8dff'];
const textOf=v=>{if(!v)return'';if(typeof v==='string')return v;if(Array.isArray(v))return textOf(v[0]);return v.title||v.label||v.text||v.name||''};
function strengthen(f){return textOf(f?.favorable_signals)||textOf(f?.watch_next)||textOf(f?.signal_convergence?.strong_signals)||'De nouveaux signaux indépendants allant dans le même sens.'}
function weaken(f){return textOf(f?.falsification)||textOf(f?.unfavorable_signals)||textOf(f?.signal_convergence?.weak_signals)||'Un signal contradictoire fort ou un changement de contexte.'}
function summary(f){return clip(f?.summary||f?.public_summary||f?.why_now||f?.explanation||'Providence relie les signaux observés, leur convergence et l’horizon temporel pour mettre à jour cette trajectoire.',240)}
async function getRows(){try{const r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)return[];const s=await r.json();return (s.forecasts||[]).filter(active).sort((a,b)=>score(b)-score(a)).slice(0,3)}catch{return[]}}
function addHitAreas(){const svg=$('.ptl-graph');if(!svg||svg.querySelector('.ptl-branch-hit'))return;const ns='http://www.w3.org/2000/svg';$$('.ptl-branch').forEach((p,i)=>{const hit=document.createElementNS(ns,'path');hit.setAttribute('class','ptl-branch-hit');hit.setAttribute('d',p.getAttribute('d')||'');hit.dataset.branch=String(i);hit.setAttribute('aria-label',`Explorer la trajectoire ${i+1}`);svg.appendChild(hit)})}
function ensurePanel(){const stage=$('.ptl-stage');if(!stage)return null;if($('.ptl-focus-panel'))return $('.ptl-focus-panel');const scrim=document.createElement('button');scrim.className='ptl-focus-scrim';scrim.type='button';scrim.setAttribute('aria-label','Fermer la trajectoire sélectionnée');const panel=document.createElement('section');panel.className='ptl-focus-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-label','Détail de la trajectoire');panel.innerHTML=`<div class="ptl-focus-head"><span class="ptl-focus-kicker"><i></i>Trajectoire sélectionnée</span><button class="ptl-focus-close" type="button" aria-label="Fermer">×</button></div><div class="ptl-focus-body" id="ptlFocusBody"></div>`;const hint=document.createElement('div');hint.className='ptl-focus-hint';hint.innerHTML='<i></i>Touchez une branche ou un scénario pour explorer';stage.append(scrim,panel,hint);return panel}
function wireCards(rows,open){const cards=$$('.ptl-live-branches .p15-forecast-card');cards.forEach((card,i)=>{if(!rows[i])return;card.dataset.branch=String(i);card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label',`Explorer ${title(rows[i])}`);card.addEventListener('click',()=>open(i));card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(i)}})})}
function wirePaths(open){$$('.ptl-branch-hit').forEach((p,i)=>{p.addEventListener('click',()=>open(i))});$$('.ptl-branch').forEach((p,i)=>{p.dataset.branch=String(i);p.addEventListener('click',()=>open(i))})}
function init(rows){if(!rows.length)return;const stage=$('.ptl-stage'),panel=ensurePanel();if(!stage||!panel)return;addHitAreas();let current=-1;const paths=$$('.ptl-branch'),cards=$$('.ptl-live-branches .p15-forecast-card');const body=$('#ptlFocusBody');
 const reset=()=>{stage.classList.remove('is-focused');stage.removeAttribute('data-focus');paths.forEach(x=>x.classList.remove('is-active'));cards.forEach(x=>x.classList.remove('is-active'));current=-1};
 const render=i=>{const f=rows[i];if(!f)return;current=i;const color=colors[i%colors.length];stage.classList.add('is-focused');stage.dataset.focus=String(i);panel.style.setProperty('--focus',color);paths.forEach((x,j)=>x.classList.toggle('is-active',j===i));cards.forEach((x,j)=>x.classList.toggle('is-active',j===i));const delta=Number(f?.probability_delta_points)||0;const horizon=f?.horizon_label||f?.horizon_tier||'Horizon actif';const region=f?.region||f?.geography||'Monde';body.innerHTML=`
   <h4>${esc(title(f))}</h4>
   <div class="ptl-focus-prob"><strong>${prob(f)}%</strong><span><b>${esc(region)} · ${esc(horizon)}</b><span>${conf(f)?`Confiance ${conf(f)}%`:''}${delta?` · ${delta>0?'+':''}${delta} pts`:''}</span></span></div>
   <p>${esc(summary(f))}</p>
   <div class="ptl-focus-shifts"><div class="ptl-shift up"><small>Ce qui renforcerait cette branche</small><b>${esc(clip(strengthen(f),130))}</b></div><div class="ptl-shift down"><small>Ce qui pourrait la faire basculer</small><b>${esc(clip(weaken(f),130))}</b></div></div>
   <div class="ptl-focus-alt-title">Comparer avec les autres futurs</div>
   <div class="ptl-focus-alts">${rows.map((x,j)=>`<button type="button" class="ptl-alt ${j===i?'active':''}" data-alt="${j}"><b>${esc(clip(title(x),44))}</b><span>${prob(x)}% · ${esc(x?.horizon_label||x?.horizon_tier||'')}</span></button>`).join('')}</div>
   <div class="ptl-focus-actions"><a href="/predictions/">Voir le résultat complet</a><a href="/analyst/">Interroger Providence →</a></div>`;
   body.querySelectorAll('[data-alt]').forEach(b=>b.addEventListener('click',()=>render(Number(b.dataset.alt))));panel.querySelector('.ptl-focus-close')?.focus({preventScroll:true});
 };
 wireCards(rows,render);wirePaths(render);panel.querySelector('.ptl-focus-close')?.addEventListener('click',reset);$('.ptl-focus-scrim')?.addEventListener('click',reset);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&current>=0)reset()});
}
async function boot(){const rows=await getRows();let tries=0;const attach=()=>{if($$('.ptl-live-branches .p15-forecast-card').length||tries>30){init(rows);return}tries++;setTimeout(attach,100)};attach()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();