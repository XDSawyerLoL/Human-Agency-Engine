(() => {
  'use strict';
  const $=s=>document.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const H={immediate:'≤ 72 heures',near:'Jours à semaines',medium:'Mois à venir',long:'1 à 3 ans',strategic:'3 à 5 ans',deep:'5 ans et +'};
  const ORDER=['immediate','near','medium','long','strategic','deep'];
  let rows=[];
  const fmtDate=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?'—':new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric'}).format(d)};
  const sourceNames=f=>(f?.consolidation?.source_providers||[]).map(x=>x.label||x.key).filter(Boolean);
  const favorable=f=>Number(f?.external_signal_counts?.favorable||0);
  const contrary=f=>Number(f?.external_signal_counts?.contrary||0);

  function card(f){
    const p=Math.round(Number(f?.probability?.percent||0));
    const sources=sourceNames(f);
    return `<article class="ref7-card" data-domain="${esc(f.domain||'')}" data-tier="${esc(f.horizon_tier||'')}">
      <div class="ref7-top"><span class="ref7-origin">RÉF. FUTURE ENGINE</span><span class="ref7-domain">${esc(f.domain_label||f.domain||'Monde')}</span><span class="ref7-region">${esc(f.region||'Monde')}</span><span class="ref7-confidence">solidité ${esc(f.confidence||'—')}%</span></div>
      <h3>${esc(f.title||'Scénario')}</h3><p class="ref7-summary">${esc(f.summary||'')}</p>
      <div class="ref7-main"><div class="ref7-ring" style="--p:${Math.max(0,Math.min(100,p))}"><strong>${p}<small>%</small></strong></div><div class="ref7-facts">
        <div><small>ÉCHÉANCE</small><b>${esc(fmtDate(f.target_date))}</b></div><div><small>HORIZON</small><b>${esc(H[f.horizon_tier]||f.horizon_label||'—')}</b></div>
        <div><small>SIGNAUX +</small><b class="ref7-up">↗ ${favorable(f)} favorables</b></div><div><small>SIGNAUX −</small><b class="ref7-down">↘ ${contrary(f)} contraires</b></div></div></div>
      <div class="ref7-chips">${(f.human_needs||[]).map(x=>`<span class="ref7-chip">${esc(x)}</span>`).join('')}${sources.map(x=>`<span class="ref7-chip ref7-source">${esc(x)}</span>`).join('')}</div>
      <div class="ref7-foot"><em>Probabilité historique importée · pas recalculée par ÉVIDENCE</em>${f.reference_url?`<a class="ref7-link" href="${esc(f.reference_url)}" target="_blank" rel="noopener noreferrer">Analyse source ↗</a>`:''}</div>
    </article>`;
  }

  function filters(){
    const q=$('#refSearch')?.value.trim().toLowerCase()||'';
    const d=$('#refDomain')?.value||''; const h=$('#refHorizon')?.value||''; const s=$('#refSource')?.value||'';
    return rows.filter(f=>{const hay=`${f.title} ${f.summary} ${f.region} ${f.domain_label} ${sourceNames(f).join(' ')}`.toLowerCase();return(!q||hay.includes(q))&&(!d||f.domain===d)&&(!h||f.horizon_tier===h)&&(!s||sourceNames(f).includes(s));});
  }

  function renderPredictionCatalog(){
    const grid=$('#futureReferenceGrid'); if(!grid)return;
    const out=filters(); grid.innerHTML=out.length?out.map(card).join(''):'<div class="ref7-empty">Aucune référence ne correspond à ces filtres.</div>';
    const count=$('#futureReferenceCount'); if(count)count.textContent=`${out.length} références actives`;
  }

  function setupFilters(){
    const domains=[...new Set(rows.map(f=>f.domain).filter(Boolean))].sort();
    const sources=[...new Set(rows.flatMap(sourceNames))].sort((a,b)=>a.localeCompare(b,'fr'));
    const d=$('#refDomain'); if(d)d.innerHTML='<option value="">Tous les domaines</option>'+domains.map(k=>`<option value="${esc(k)}">${esc(rows.find(x=>x.domain===k)?.domain_label||k)}</option>`).join('');
    const h=$('#refHorizon'); if(h)h.innerHTML='<option value="">Tous les horizons</option>'+ORDER.map(k=>`<option value="${k}">${H[k]}</option>`).join('');
    const s=$('#refSource'); if(s)s.innerHTML='<option value="">Toutes les sources</option>'+sources.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');
    ['#refSearch','#refDomain','#refHorizon','#refSource'].forEach(sel=>$(sel)?.addEventListener(sel==='#refSearch'?'input':'change',renderPredictionCatalog));
  }

  function renderHorizonCatalog(){
    const board=$('#futureReferenceHorizons'); if(!board)return;
    board.innerHTML=ORDER.map(k=>{const group=rows.filter(f=>f.horizon_tier===k).sort((a,b)=>Number(b.probability?.percent||0)-Number(a.probability?.percent||0));return `<section class="ref7-horizon"><header><h3>${H[k]}</h3><strong>${group.length}</strong></header><div class="ref7-grid">${group.length?group.map(card).join(''):'<div class="ref7-empty">Aucune référence active sur cet horizon.</div>'}</div></section>`}).join('');
  }

  async function init(){
    try{const r=await fetch('/api/reference-forecasts',{cache:'no-store'});const data=await r.json();if(!r.ok)throw new Error(data?.error||`HTTP ${r.status}`);rows=Array.isArray(data.forecasts)?data.forecasts:[];
      const total=$('#futureReferenceTotal');if(total)total.textContent=`${rows.length} références actives`;
      setupFilters();renderPredictionCatalog();renderHorizonCatalog();
    }catch(e){const target=$('#futureReferenceGrid')||$('#futureReferenceHorizons');if(target)target.innerHTML=`<div class="ref7-empty">Catalogue Future Engine indisponible : ${esc(e.message)}</div>`;}
  }
  init();
})();