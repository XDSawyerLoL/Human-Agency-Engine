(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const pct = v => `${Math.round(Number(v)||0)}%`;
  const fmtDate = v => { const d=new Date(v); return Number.isNaN(d.getTime())?'—':new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(d); };
  let snapshot=null, analytics=null;

  async function j(url,options){ const r=await fetch(url,{cache:'no-store',...(options||{})}); const data=await r.json(); if(!r.ok) throw new Error(data?.error||`HTTP ${r.status}`); return data; }

  function renderKpis(){
    const k=analytics?.kpis||{};
    $('[data-kpi="forecasts"]').textContent=k.active_forecasts??'—';
    $('[data-kpi="signals"]').textContent=k.signals_analyzed??'—';
    $('[data-kpi="probability"]').textContent=pct(k.average_probability);
    $('[data-kpi="countries"]').textContent=k.countries_covered??'—';
    $('[data-kpi="confidence"]').textContent=pct(k.average_confidence);
  }

  function renderSignalChart(){
    const rows=analytics?.signal_volume_7d||[]; const max=Math.max(1,...rows.map(x=>Number(x.count)||0));
    $('#signalChart').innerHTML=rows.map(x=>`<div class="d6-bar"><b>${esc(x.count)}</b><i style="--h:${Math.max(4,Math.round((Number(x.count)||0)/max*210))}px"></i><small>${esc(String(x.date).slice(5))}</small></div>`).join('')||'<div class="d6-loading">Historique en cours de constitution.</div>';
  }

  function renderDomains(){
    const obj=analytics?.recent_domain_distribution||{}; const rows=Object.entries(obj).sort((a,b)=>b[1]-a[1]); const max=Math.max(1,...rows.map(x=>Number(x[1])||0));
    $('#domainBars').innerHTML=rows.map(([k,n])=>`<div class="d6-domain"><span>${esc(k)}</span><i style="--w:${Math.round(Number(n)/max*100)}%"></i><b>${esc(n)}</b></div>`).join('')||'<div class="d6-loading">Pas encore assez de cycles.</div>';
  }

  function renderSources(){
    const rows=analytics?.predictions_by_source||[];
    $('#sourceBoard').innerHTML=rows.map(s=>`<article class="d6-source-stat ${s.mode==='référence'?'ref':''}"><small>${esc(String(s.mode||'').toUpperCase())}</small><strong>${esc(s.count)}</strong><b>${esc(s.label)}</b></article>`).join('');
    $('#fusedSources').innerHTML=(analytics?.sources_fused||[]).map(s=>`<span class="d6-chip" title="${esc(s.role||'')}">${esc(s.label)}</span>`).join('')||'<span class="d6-chip">ÉVIDENCE</span>';
  }

  function renderFeed(){
    const rows=analytics?.realtime_signal_feed||[];
    $('#signalFeed').innerHTML=rows.map(s=>{
      const inner=`<i></i><div><b>${esc(s.title||'Signal')}</b><small>${esc(s.source_label||s.source_key||'Source')} · ${esc(s.domain||'')} · ${esc(s.geography||'Monde')}</small></div><time>${esc(fmtDate(s.observed_at))}</time>`;
      return s.url?`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${inner}</a>`:`<div>${inner}</div>`;
    }).join('')||'<div class="d6-loading">Le prochain cycle alimentera le flux.</div>';
    $('#feedTime').textContent=`${rows.length} signaux récents`;
  }

  function weatherLevel(f){ const impacts=f.impact_analysis||[]; const top=Math.max(0,...impacts.map(x=>Number(x.expected)||0)); return top>=70?'critical':top>=52?'high':'moderate'; }
  function renderWeather(){
    const w=analytics?.weather||{}; $('#windyMap').src=w.map_embed_url||''; $('#windyNote').textContent=w.note||'';
    const rows=(snapshot?.forecasts||[]).filter(f=>['natural_hazards','weather_climate'].includes(f.domain)).slice(0,6);
    $('#weatherAlerts').innerHTML=rows.map(f=>`<article class="d6-alert ${weatherLevel(f)}"><small>${esc((f.region||'Monde').toUpperCase())} · ${pct(f.probability?.percent)}</small><h3>${esc(f.title||f.headline)}</h3><p>${esc(f.summary||f.why_now||'')}</p></article>`).join('')||'<div class="d6-loading">Aucune alerte météo/environnementale publiée sur ce cycle.</div>';
  }

  function renderScenarioSelect(){
    const rows=snapshot?.forecasts||[]; $('#scenarioSelect').innerHTML=rows.map(f=>`<option value="${esc(f.scenario_key)}">${esc(`${f.probability?.percent||'—'}% · ${f.title||f.headline}`)}</option>`).join('');
    if(rows.length) renderDossier(rows[0]);
    $('#scenarioSelect').onchange=()=>{ const f=rows.find(x=>String(x.scenario_key)===String($('#scenarioSelect').value)); if(f) renderDossier(f); };
  }

  function impactList(f){ return (f.impact_analysis||[]).map(x=>`<div class="d6-impact"><span>${esc(x.label)}</span><i style="--w:${Math.round(Number(x.expected)||0)}%"></i><b>${esc(x.level)} ${Math.round(Number(x.expected)||0)}</b></div>`).join(''); }
  function confidence(f){ const c=f.confidence_breakdown||{}; return `<div class="d6-confidence"><div><small>SCORE</small><strong>${pct(c.score)}</strong></div><div><small>FIABILITÉ</small><strong>${pct(c.reliability)}</strong></div><div><small>FRAÎCHEUR</small><strong>${pct(c.freshness)}</strong></div><div><small>CONVERGENCE</small><strong>${pct(c.convergence)}</strong></div><div><small>DIVERSITÉ</small><strong>${pct(c.diversity)}</strong></div><div><small>SOURCES</small><strong>${esc(c.source_count??0)}</strong></div></div><p>${esc(c.formula||'')}</p>`; }
  function actions(f){ const d=f.decision_brief||{}; return `<div class="d6-decision-main"><small>RECOMMANDATION · ${esc(String(d.level||'observer').toUpperCase())}</small><strong>${esc(d.primary_action||'Surveiller les prochains signaux.')}</strong><p>${esc(d.cost_of_inaction||'')}</p></div><div class="d6-actions">${(d.do_now||[]).map((x,i)=>`<div class="d6-action"><b>${i+1}. ${esc(x)}</b><span>${i===0?'prioritaire':'mesure préparatoire'}</span></div>`).join('')}</div><p><b>À éviter :</b> ${esc(d.avoid||'')}</p>`; }
  function linked(f){ return (f.linked_signals||[]).map(s=>{const inner=`<b>${esc(s.title)}</b><small>${esc(s.source_label)}${s.trust!==null?` · fiabilité ${esc(s.trust)}/100`:''} · ${esc(fmtDate(s.observed_at))}</small>`;return s.url?`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${inner}</a>`:`<div>${inner}</div>`;}).join('')||'<div>Aucun signal détaillé publié.</div>'; }
  function ensemble(f){ const e=f.shadow_ensemble; if(!e)return '<p>Ensemble shadow non disponible.</p>'; return `<div class="d6-ensemble">${(e.components||[]).map(x=>`<div><span>${esc(x.label)}</span><b>${pct(x.percent)}</b></div>`).join('')}</div><p><b>Ensemble shadow : ${pct(e.percent)}</b>. ${esc(e.independence_warning||'')}</p>`; }

  function renderDossier(f){
    $('#dossier').innerHTML=`<div class="d6-dossier-hero"><div><small>${esc((f.domain||'monde').toUpperCase())} · ${esc(f.region||'Monde')} · ${esc(f.horizon_label||f.horizon_tier||'')}</small><h3>${esc(f.title||f.headline)}</h3><p>${esc(f.summary||f.why_now||'')}</p></div><div class="d6-score"><strong>${pct(f.probability?.percent)}</strong><span>probabilité ÉVIDENCE<br>confiance ${pct(f.confidence_breakdown?.score)}</span></div></div>
      <div class="d6-dossier-grid"><article class="d6-block span2"><small>ANALYSE D’IMPACT</small><h4>Conséquences anticipées par dimension</h4><div class="d6-impact-list">${impactList(f)}</div></article><article class="d6-block"><small>CALCUL DE CONFIANCE</small><h4>Pourquoi faire confiance à ce signal ?</h4>${confidence(f)}</article>
      <article class="d6-block span2"><small>UNE FOIS QU’ON SAIT, ON FAIT QUOI ?</small><h4>Decision Layer</h4>${actions(f)}</article><article class="d6-block"><small>SIGNAUX LIÉS</small><h4>Ce qui nourrit la prévision</h4><div class="d6-signal-list">${linked(f)}</div></article>
      <article class="d6-block"><small>FORECASTER ENSEMBLE</small><h4>Comparaison interne</h4>${ensemble(f)}</article><article class="d6-block span2"><small>CONTRE-FACTUEL</small><h4>Et si le signal changeait ?</h4><div class="d6-counter"><button class="d6-btn" data-cf="up">Le signal se renforce</button><button class="d6-btn secondary" data-cf="down">Le signal s’affaiblit</button><button class="d6-btn secondary" data-cf="reset">Réinitialiser</button></div><div id="cfResult" class="d6-counter-result">Probabilité actuelle : ${pct(f.probability?.percent)}. Testez une hypothèse.</div></article>
      <article class="d6-block"><small>RÉFUTATION</small><h4>Comment cette prévision peut échouer</h4><p>${esc(f.falsification||'Le scénario ne se matérialise pas dans la fenêtre annoncée.')}</p></article></div>`;
    document.querySelectorAll('[data-cf]').forEach(btn=>btn.onclick=()=>runCounterfactual(f,btn.dataset.cf));
  }

  async function runCounterfactual(f,mode){
    if(mode==='reset'){ $('#cfResult').textContent=`Probabilité actuelle : ${pct(f.probability?.percent)}. Testez une hypothèse.`; return; }
    $('#cfResult').textContent='Simulation…';
    try{
      const label=mode==='up'?(f.probability_up_if||f.favorable_signals||['Précurseur favorable'])[0]:(f.probability_down_if||f.contrary_signals||['Précurseur contraire'])[0];
      const data=await j(`/api/counterfactual/${encodeURIComponent(f.scenario_key)}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({changes:[{label,direction:mode,strength:2}]})});
      $('#cfResult').innerHTML=`<b>${esc(data.base_probability)}% → ${esc(data.simulated_probability)}%</b> (${data.delta_points>0?'+':''}${esc(data.delta_points)} points) · intervalle ${esc(data.interval_percent?.[0])}–${esc(data.interval_percent?.[1])}%<br><small>${esc(data.note)}</small>`;
    }catch(e){$('#cfResult').textContent=`Simulation indisponible : ${e.message}`;}
  }

  async function runSports(){
    const box=$('#sportsLab'); box.innerHTML='<div class="d6-loading">Backtest en cours sur l’historique StatsBomb…</div>';
    try{ const d=await j('/api/calibration/sports'); box.innerHTML=`<p><b>${esc(d.competition)} · ${esc(d.season)}</b></p><p>${esc(d.training_matches)} matchs d’entraînement · ${esc(d.test_matches)} matchs de test</p><div class="d6-confidence"><div><small>BRIER 3-ISSUES</small><strong>${esc(d.multiclass_brier)}</strong></div><div><small>DOMICILE</small><strong>${pct(d.baseline_probabilities?.home)}</strong></div><div><small>NUL</small><strong>${pct(d.baseline_probabilities?.draw)}</strong></div><div><small>EXTÉRIEUR</small><strong>${pct(d.baseline_probabilities?.away)}</strong></div></div><p>${esc(d.interpretation)}</p><small>${esc(d.transfer_warning)}</small>`; }catch(e){box.innerHTML=`<p>Lab indisponible : ${esc(e.message)}</p><button id="runSports" class="d6-btn">Réessayer</button>`; $('#runSports')?.addEventListener('click',runSports);}
  }

  async function renderBench(){
    try{const d=await j('/api/benchmarks');const rows=[['FutureEval',d.futureeval],['Sport',d.sports],['Météo',d.weather],['Marchés',d.markets]];$('#benchmarkBoard').innerHTML=rows.map(([name,x])=>`<article><small>${esc(name.toUpperCase())}</small><strong>${esc(x?.status||'—')}</strong><span>${esc(x?.provider||x?.reason||'')}</span></article>`).join('');}catch(e){$('#benchmarkBoard').innerHTML=`<div class="d6-loading">${esc(e.message)}</div>`;}
  }

  async function init(){
    try{
      [snapshot,analytics]=await Promise.all([j('/api/snapshot'),j('/api/analytics')]);
      $('#liveState').textContent='LIVE'; renderKpis(); renderSignalChart(); renderDomains(); renderSources(); renderFeed(); renderWeather(); renderScenarioSelect(); renderBench();
      $('#runSports')?.addEventListener('click',runSports);
    }catch(e){$('#liveState').textContent='ERREUR'; document.querySelector('.d6-shell').insertAdjacentHTML('afterbegin',`<div class="d6-panel">Impossible de charger Decision Intelligence : ${esc(e.message)}</div>`);}
  }
  init();
})();