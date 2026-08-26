(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const clamp = (v,a,b) => Math.max(a,Math.min(b,Number(v)||0));

  const DOMAIN = {
    natural_hazards:'Risques naturels', weather_climate:'Météo & climat', cyber_technology:'Cyber & espace',
    public_health:'Santé', financial_stress:'Finance', energy:'Énergie', economy_labor:'Économie & emploi',
    supply_fuel:'Commerce & logistique', social_collective_behavior:'Comportements collectifs',
    geopolitics_security:'Géopolitique', regulation_policy:'Décisions & adaptation', transport_mobility:'Transport'
  };
  const HORIZONS = {
    immediate:{label:'À surveiller ≤ 72 h',short:'≤ 72 h',sub:'Événements imminents à fort impact.',order:0,icon:'clock'},
    near:{label:'Jours à semaines',short:'Jours à semaines',sub:'Tendances à court terme qui se dessinent.',order:1,icon:'calendar'},
    medium:{label:'Mois',short:'Mois',sub:'Évolutions structurelles à horizon moyen.',order:2,icon:'bars'},
    long:{label:'1 à 3 ans',short:'1 à 3 ans',sub:'Transformations à moyen terme.',order:3,icon:'trend'},
    strategic:{label:'3 à 5 ans',short:'3 à 5 ans',sub:'Grandes tendances structurelles.',order:4,icon:'globe'}
  };
  const ICONS = {
    clock:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"></circle><path d="M12 7v5l3 2"></path></svg>',
    calendar:'<svg viewBox="0 0 24 24"><rect x="4" y="6" width="16" height="14" rx="2"></rect><path d="M8 3v6M16 3v6M4 10h16"></path></svg>',
    bars:'<svg viewBox="0 0 24 24"><path d="M5 19V12M10 19V8M15 19V5M20 19V3"></path></svg>',
    trend:'<svg viewBox="0 0 24 24"><path d="M4 17l5-5 4 3 7-8"></path><path d="M16 7h4v4"></path></svg>',
    globe:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"></path></svg>'
  };
  let snapshot = null;
  let expandedTier = null;

  const prob = f => Number.isFinite(Number(f?.probability?.percent)) ? Math.round(Number(f.probability.percent)) : Math.round(clamp(f?.probability?.estimate,0,1)*100);
  const solidity = f => Math.round(Number(f?.consolidation?.score ?? f?.confidence ?? 0));
  const tier = f => f?.horizon_tier || f?.time_window?.tier || 'near';
  const region = f => f?.region || f?.geography || f?.evidence?.[0]?.facts?.geography || 'Monde';
  const title = f => f?.title || f?.headline || f?.outcome || 'Scénario en formation';
  const summary = f => f?.summary || f?.public_summary || f?.what_we_know || f?.why_now || '';
  const sourceLabels = f => (f?.consolidation?.source_providers || []).map(x=>x.label||x.key).filter(Boolean);
  const favorable = f => (f?.favorable_signals || f?.probability_up_if || []).filter(Boolean);
  const contrary = f => (f?.contrary_signals || f?.probability_down_if || []).filter(Boolean);
  const trajectory = f => f?.probability_direction === 'rising' || f?.trajectory === 'building' ? 'En hausse' : f?.probability_direction === 'falling' ? 'En baisse' : f?.trajectory === 'forming' ? 'En formation' : 'Stable';
  const level = f => { const s=solidity(f); return s>=75?'Solide':s>=58?'Consolidé':s>=42?'En formation':'Exploratoire'; };
  const formatCompact = n => {
    n = Number(n); if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('fr-FR',{notation:n>=10000?'compact':'standard',maximumFractionDigits:1}).format(n);
  };
  const relative = t => {
    if(!t) return '—'; const d=new Date(t); if(Number.isNaN(d.getTime())) return '—'; const s=Math.max(0,(Date.now()-d.getTime())/1000);
    return s<60?'à l’instant':s<3600?`il y a ${Math.floor(s/60)} min`:s<86400?`il y a ${Math.floor(s/3600)} h`:`il y a ${Math.floor(s/86400)} j`;
  };
  const domainIcon = d => {
    const paths = {
      energy:'<path d="M13 2L5 14h7l-1 8 8-13h-7z"></path>', public_health:'<path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.7A4 4 0 0 1 19 11c0 5.5-7 10-7 10z"></path><path d="M8 13h2l1-2 2 4 1-2h2"></path>',
      cyber_technology:'<rect x="5" y="10" width="14" height="10" rx="2"></rect><path d="M8 10V7a4 4 0 0 1 8 0v3"></path>', transport_mobility:'<path d="M3 15l18-6-7 12-3-6-8 0z"></path>',
      weather_climate:'<path d="M12 3c3 5 6 8 6 12a6 6 0 0 1-12 0c0-4 3-7 6-12z"></path>', natural_hazards:'<path d="M4 18h16L13 5l-3 6-2-2z"></path>',
      economy_labor:'<rect x="4" y="7" width="16" height="12" rx="2"></rect><path d="M9 7V5h6v2M4 12h16"></path>', financial_stress:'<path d="M4 17l5-5 4 3 7-8"></path><path d="M16 7h4v4"></path>',
      geopolitics_security:'<circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3c3 3 3 15 0 18"></path>', supply_fuel:'<path d="M4 7h10v10H4zM14 10h3l3 3v4h-6z"></path><circle cx="8" cy="18" r="1.6"></circle><circle cx="17" cy="18" r="1.6"></circle>',
      social_collective_behavior:'<circle cx="9" cy="9" r="3"></circle><circle cx="16" cy="10" r="2.5"></circle><path d="M4 19c0-4 2-6 5-6s5 2 5 6M13 19c0-3 1.5-5 4-5s4 2 4 5"></path>',
      regulation_policy:'<path d="M5 5h14M8 5v14M16 5v14M5 19h14"></path><path d="M8 10h8M8 14h8"></path>'
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[d]||paths.geopolitics_security}</svg>`;
  };

  function ring(p, size='small') {
    return `<div class="prob-ring ${size}" style="--p:${clamp(p,0,100)}"><span>${p}<em>%</em></span></div>`;
  }

  function sparkline(f) {
    let values = (f?.probability_history||[]).map(x=>Number(x?.percent)).filter(Number.isFinite).slice(-8);
    if (!values.length) values=[prob(f),prob(f)];
    if (values.length===1) values=[values[0],values[0]];
    const w=210,h=94,pad=8,min=0,max=100;
    const pts=values.map((v,i)=>[pad+i*(w-pad*2)/(values.length-1),h-pad-(clamp(v,min,max)-min)*(h-pad*2)/(max-min)]);
    const line=pts.map(([x,y])=>`${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    const [lx,ly]=pts.at(-1);
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="Trajectoire de probabilité"><defs><linearGradient id="sparkGrad" x1="0" x2="1"><stop stop-color="#4bdcff"/><stop offset="1" stop-color="#8d57ff"/></linearGradient></defs><g class="grid"><path d="M8 24H202M8 47H202M8 70H202"></path></g><polyline points="${line}" fill="none" stroke="url(#sparkGrad)" stroke-width="3" vector-effect="non-scaling-stroke"></polyline><circle cx="${lx}" cy="${ly}" r="4" fill="#a15cff"></circle></svg>`;
  }

  function primaryCard(f) {
    const p=prob(f), s=solidity(f), h=HORIZONS[tier(f)]||HORIZONS.near, up=favorable(f), down=contrary(f);
    const trend=trajectory(f); const trendClass=trend==='En baisse'?'down':trend==='En hausse'?'up':'';
    return `<article class="primary-card">
      <div class="primary-head"><span class="primary-label">PRÉDICTION PRINCIPALE <b>★</b></span><small>Mise à jour : ${esc(relative(snapshot?.generated_at))}</small></div>
      <div class="primary-body">
        <div class="primary-score"><strong>${p}</strong><em>%</em></div>
        <div class="primary-copy">
          <h2>${esc(title(f))}</h2>
          <div class="primary-window">${esc(f?.time_window?.human||h.short)}</div>
          <div class="meta-line"><span>${ICONS.globe}<small>RÉGION</small><b>${esc(region(f))}</b></span><span>${domainIcon(f.domain)}<small>DOMAINE</small><b>${esc(DOMAIN[f.domain]||f.domain||'Monde')}</b></span></div>
          <p>${esc(summary(f))}</p>
          <div class="status-row"><span class="status ${trendClass}"><b>${trend==='En hausse'?'↑':trend==='En baisse'?'↓':'•'} ${esc(trend.toUpperCase())}</b><small>${f?.probability_delta_points?`${Number(f.probability_delta_points)>0?'+':''}${Number(f.probability_delta_points).toFixed(0)} pts`:'trajectoire actuelle'}</small></span><span class="status solid"><b>♢ ${esc(level(f).toUpperCase())}</b><small>signal ${s||'—'}/100</small></span><span class="status horizon"><b>▣ HORIZON</b><small>${esc(h.short)}</small></span></div>
        </div>
        <div class="trajectory-panel"><small>TRAJECTOIRE DE PROBABILITÉ</small>${sparkline(f)}<div class="axis"><span>0%</span><span>50%</span><span>100%</span></div><button class="trajectory-button" data-detail="primary">Voir la trajectoire <span>→</span></button></div>
      </div>
      <div class="primary-bottom"><div><span class="plus">+</span><p><small>CE QUI RENFORCE</small><b>${esc(up[0]||'Confirmation de nouveaux précurseurs')}</b></p></div><div><span class="minus">•</span><p><small>CE QUI FRAGILISE</small><b>${esc(down[0]||'Normalisation des indicateurs intermédiaires')}</b></p></div></div>
      ${detailDrawer(f,'primary')}
    </article>`;
  }

  function detailDrawer(f,id) {
    const up=favorable(f).slice(0,4), down=contrary(f).slice(0,4), chain=(f?.causal_chain||[]).filter(Boolean), sources=sourceLabels(f).slice(0,6);
    return `<div class="detail-drawer" id="detail-${id}" hidden><div><small>POURQUOI MAINTENANT</small><p>${esc(f?.why_now||f?.what_we_know||summary(f))}</p></div>${chain.length?`<div><small>CHAÎNE PROBABLE</small><p class="chain">${chain.map(x=>`<span>${esc(x)}</span>`).join('<i>→</i>')}</p></div>`:''}<div class="detail-columns"><div><small>RENFORCEMENT</small><ul>${up.map(x=>`<li>${esc(x)}</li>`).join('')||'<li>Pas de renforcement supplémentaire publié.</li>'}</ul></div><div><small>INVALIDATION</small><ul>${down.map(x=>`<li>${esc(x)}</li>`).join('')||`<li>${esc(f?.falsification||'Le résultat n’apparaît pas dans la fenêtre annoncée.')}</li>`}</ul></div></div><div class="detail-sources"><small>SOURCES</small>${sources.map(x=>`<span>${esc(x)}</span>`).join('')}</div></div>`;
  }

  function miniCard(f,idx) {
    const p=prob(f), h=HORIZONS[tier(f)]||HORIZONS.near;
    return `<article class="mini-card"><div class="mini-left">${ring(p)}<div><h3>${esc(title(f))}</h3><p class="mini-meta">${esc(f?.time_window?.human||h.short)} <span>•</span> ${esc(region(f))}</p><p class="mini-summary">${esc(summary(f))}</p></div></div><div class="mini-domain">${domainIcon(f.domain)}</div><button class="mini-open" aria-label="Voir le détail" data-detail="${esc(f.scenario_key||`f-${idx}`)}">↗</button>${detailDrawer(f,f.scenario_key||`f-${idx}`)}</article>`;
  }

  function horizonRow(key, rows) {
    const meta=HORIZONS[key]; const visible=expandedTier===key?rows:rows.slice(0,3);
    const cards = visible.length ? visible.map((f,i)=>miniCard(f,i)).join('') : '<div class="row-empty">Aucun scénario assez solide pour cet horizon.</div>';
    const canExpand=rows.length>3;
    return `<section class="horizon-row" data-tier="${key}"><div class="horizon-label"><span class="horizon-icon">${ICONS[meta.icon]}</span><div><h2>${esc(meta.label)}</h2><p>${esc(meta.sub)}</p></div></div><div class="row-cards ${expandedTier===key?'expanded':''}">${cards}${canExpand?`<button class="view-all" data-expand="${key}">${expandedTier===key?'Réduire':'Voir tout'} <span>→</span></button>`:''}</div></section>`;
  }

  function renderBoard(rows) {
    const groups={immediate:[],near:[],medium:[],long:[],strategic:[]};
    rows.forEach(f => (groups[tier(f)] ||= []).push(f));
    Object.values(groups).forEach(arr=>arr.sort((a,b)=>commercialScore(b)-commercialScore(a)));
    $('#horizonBoard').innerHTML = ['immediate','near','medium','long','strategic'].map(k=>horizonRow(k,groups[k])).join('');
  }

  function commercialScore(f) { return prob(f)+solidity(f)*.25+(Number(f?.commercial_priority)||.55)*10-(HORIZONS[tier(f)]?.order||0)*2; }

  function renderSources(rows) {
    const sourceMap=new Map();
    rows.flatMap(f=>f?.consolidation?.source_providers||[]).forEach(s=>sourceMap.set(s.key||s.label,s.label||s.key));
    const labels=[...sourceMap.values()].filter(Boolean);
    $('#sourceCount').textContent=labels.length||'—';
    $('#sourceGrid').innerHTML = labels.slice(0,9).map(x=>`<span>${esc(x)}</span>`).join('') || '<span>Sources en consolidation</span>';
    $('#sourceMore').textContent = labels.length>9 ? `+ ${labels.length-9} autres sources actives` : 'Sources publiques vérifiées par le moteur';
  }

  function render(data) {
    snapshot=data;
    const rows=[...(data?.forecasts||[])].filter(f=>!['resolved','invalidated'].includes(f?.status));
    $('#metricForecasts').textContent=formatCompact(rows.length);
    $('#metricSignals').textContent=formatCompact(data?.summary?.signals_considered ?? data?.summary?.evidence_items_considered);
    $('#metricTop').textContent=rows.length?`${Math.max(...rows.map(prob))}%`:'—';
    $('#metricForecastsMeta').textContent=rows.length?`${rows.filter(f=>f?.probability_direction==='rising').length} en renforcement`:'aucun scénario publié';
    $('#metricSignalsMeta').textContent=`${data?.summary?.source_providers ?? 'plusieurs'} sources actives`;
    $('#metricTopMeta').textContent='estimation du cycle actuel';
    $('#snapshotTime').textContent=`mis à jour ${relative(data?.generated_at)}`;
    $('#liveDot').dataset.state='live';
    const primary=[...rows].sort((a,b)=>commercialScore(b)-commercialScore(a))[0];
    $('#primaryForecast').innerHTML=primary?primaryCard(primary):'<div class="loading-card"><div><strong>Aucun scénario assez solide.</strong><small>ÉVIDENCE préfère ne rien publier plutôt que remplir l’écran avec du bruit.</small></div></div>';
    renderBoard(rows); renderSources(rows); wireDynamicEvents();
  }

  function wireDynamicEvents() {
    document.querySelectorAll('[data-detail]').forEach(btn=>btn.addEventListener('click',()=>{
      const el=document.getElementById(`detail-${CSS.escape(btn.dataset.detail)}`); if(!el) return; el.hidden=!el.hidden; btn.classList.toggle('open',!el.hidden);
    }));
    document.querySelectorAll('[data-expand]').forEach(btn=>btn.addEventListener('click',()=>{expandedTier=expandedTier===btn.dataset.expand?null:btn.dataset.expand; renderBoard(snapshot?.forecasts||[]); wireDynamicEvents();}));
  }

  async function load() {
    try {
      const r=await fetch(`/api/snapshot?t=${Date.now()}`,{cache:'no-store'}); if(!r.ok) throw new Error(`HTTP ${r.status}`); const data=await r.json(); if(!Array.isArray(data?.forecasts)) throw new Error('snapshot invalide'); render(data);
    } catch(e) {
      $('#liveDot').dataset.state='error'; $('#snapshotTime').textContent='reconnexion';
      $('#primaryForecast').innerHTML=`<div class="loading-card error"><div><strong>Le champ prédictif se reconnecte.</strong><small>${esc(e.message)}</small></div></div>`;
    }
  }

  $('#searchToggle').addEventListener('click',()=>{const d=$('#searchDrawer'); d.hidden=!d.hidden; if(!d.hidden) $('#searchInput').focus();});
  $('#searchClose').addEventListener('click',()=>$('#searchDrawer').hidden=true);
  $('#searchInput').addEventListener('input',e=>{
    if(!snapshot) return; const q=e.target.value.trim().toLowerCase();
    const rows=(snapshot.forecasts||[]).filter(f=>!q||`${title(f)} ${summary(f)} ${region(f)} ${DOMAIN[f.domain]||''}`.toLowerCase().includes(q)); renderBoard(rows); wireDynamicEvents();
  });

  load(); setInterval(load,5*60*1000);
})();
