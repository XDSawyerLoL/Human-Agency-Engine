(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const clamp = (v,a,b) => Math.max(a,Math.min(b,Number(v)||0));
  const SNAPSHOT_ENDPOINTS = ['./data/evidence-live.json', '/api/snapshot'];
  const HORIZON_ORDER = ['immediate','near','medium','long','strategic','deep'];

  const DOMAIN = {
    natural_hazards:'Risques naturels', weather_climate:'Météo & climat', cyber_technology:'Cyber & technologie',
    public_health:'Santé', financial_stress:'Finance', energy:'Énergie', economy_labor:'Économie & emploi',
    supply_fuel:'Commerce & logistique', social_collective_behavior:'Comportements collectifs',
    geopolitics_security:'Géopolitique', regulation_policy:'Décisions & régulation', transport_mobility:'Transport'
  };
  const HORIZONS = {
    immediate:{label:'À surveiller ≤ 72 h',short:'≤ 72 h',sub:'Ce qui peut basculer très vite.',order:0,icon:'clock'},
    near:{label:'Jours à semaines',short:'Jours à semaines',sub:'Les prochaines conséquences en formation.',order:1,icon:'calendar'},
    medium:{label:'Mois à venir',short:'Mois',sub:'Ce qui peut devenir visible dans les prochains mois.',order:2,icon:'bars'},
    long:{label:'1 à 3 ans',short:'1–3 ans',sub:'Transformations structurelles à moyen terme.',order:3,icon:'trend'},
    strategic:{label:'3 à 5 ans',short:'3–5 ans',sub:'Trajectoires stratégiques si les signaux persistent.',order:4,icon:'globe'},
    deep:{label:'5 ans et +',short:'5–10 ans',sub:'Scénarios conditionnels à très long terme.',order:5,icon:'deep'}
  };
  const ICONS = {
    clock:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"></circle><path d="M12 7v5l3 2"></path></svg>',
    calendar:'<svg viewBox="0 0 24 24"><rect x="4" y="6" width="16" height="14" rx="2"></rect><path d="M8 3v6M16 3v6M4 10h16"></path></svg>',
    bars:'<svg viewBox="0 0 24 24"><path d="M5 19V12M10 19V8M15 19V5M20 19V3"></path></svg>',
    trend:'<svg viewBox="0 0 24 24"><path d="M4 17l5-5 4 3 7-8"></path><path d="M16 7h4v4"></path></svg>',
    globe:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"></path></svg>',
    deep:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"></circle><circle cx="12" cy="12" r="3"></circle><path d="M12 1v3M12 20v3M1 12h3M20 12h3"></path></svg>'
  };

  let snapshot = null;
  let expandedTier = null;
  let highlightKeys = new Set();

  const prob = f => Number.isFinite(Number(f?.probability?.percent)) ? Math.round(Number(f.probability.percent)) : Math.round(clamp(f?.probability?.estimate,0,1)*100);
  const solidity = f => Math.round(Number(f?.consolidation?.score ?? f?.confidence ?? 0));
  const tier = f => f?.horizon_tier || f?.time_window?.tier || 'near';
  const region = f => f?.region || f?.geography || 'Monde';
  const title = f => f?.title || f?.headline || f?.outcome || 'Scénario en formation';
  const summary = f => f?.summary || f?.public_summary || f?.what_we_know || f?.why_now || '';
  const favorable = f => (f?.favorable_signals || f?.probability_up_if || []).filter(Boolean);
  const contrary = f => (f?.contrary_signals || f?.probability_down_if || []).filter(Boolean);
  const impacts = f => (f?.human_needs || []).filter(Boolean).slice(0,4);
  const providers = f => (f?.consolidation?.source_providers || []).filter(Boolean);
  const trajectory = f => f?.probability_direction === 'rising' || f?.trajectory === 'building' ? 'En hausse' : f?.probability_direction === 'falling' ? 'En baisse' : f?.trajectory === 'forming' ? 'En formation' : f?.probability_direction === 'new' ? 'Nouveau' : 'Stable';
  const level = f => { const s=solidity(f); return s>=75?'très solide':s>=60?'solide':s>=45?'en consolidation':'exploratoire'; };
  const keyOf = f => f?.scenario_key || f?.id || title(f);
  const safeId = v => String(v||'x').replace(/[^a-zA-Z0-9_-]/g,'-');
  const formatCompact = n => {
    n=Number(n); if(!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('fr-FR',{notation:n>=10000?'compact':'standard',maximumFractionDigits:1}).format(n);
  };
  const relative = t => {
    if(!t) return '—'; const d=new Date(t); if(Number.isNaN(d.getTime())) return '—'; const s=Math.max(0,(Date.now()-d.getTime())/1000);
    return s<60?'à l’instant':s<3600?`il y a ${Math.floor(s/60)} min`:s<86400?`il y a ${Math.floor(s/3600)} h`:`il y a ${Math.floor(s/86400)} j`;
  };
  const dateLabel = f => {
    const raw=f?.target_date || f?.time_window?.end_at; if(!raw) return HORIZONS[tier(f)]?.short||'—';
    const d=new Date(raw); if(Number.isNaN(d.getTime())) return HORIZONS[tier(f)]?.short||'—';
    return new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric'}).format(d);
  };
  const commercialScore = f => prob(f)+solidity(f)*.25+(Number(f?.commercial_priority)||.55)*10-(HORIZONS[tier(f)]?.order||0)*1.5;

  function providerClass(key='') {
    const k=String(key).toLowerCase();
    if(k.includes('gdelt')) return 'gdelt'; if(k.includes('who')) return 'who'; if(k.includes('nasa')) return 'nasa';
    if(k.includes('usgs')) return 'usgs'; if(k.includes('noaa')) return 'noaa'; if(k.includes('copernicus')) return 'copernicus';
    if(k.includes('fred')) return 'fred'; if(k.includes('forecast')) return 'forecast'; if(k.includes('metaculus')) return 'metaculus';
    return 'generic';
  }

  function domainIcon(d) {
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
  }

  function ring(p) {
    return `<div class="prob-ring v3" style="--p:${clamp(p,0,100)}"><span>${p}<em>%</em></span><small>PROBA</small></div>`;
  }

  function sourceChips(f, limit=4) {
    const rows=providers(f); const shown=rows.slice(0,limit);
    const chips=shown.map(s=>`<span class="source-chip ${providerClass(s.key)}" title="${esc(s.role||'Source contributrice')}"><i>◎</i>${esc(s.label||s.key)}</span>`).join('');
    const more=rows.length>limit?`<span class="source-chip generic">+${rows.length-limit}</span>`:'';
    return chips||'<span class="source-chip generic">ÉVIDENCE</span>'+more;
  }

  function impactChips(f) {
    const rows=impacts(f);
    return rows.length?rows.map(x=>`<span>${esc(x)}</span>`).join(''):'<span>Impact à préciser</span>';
  }

  function evidenceSources(f) {
    const rows=(f?.evidence||[]).slice(0,8);
    if(!rows.length) return '<p class="detail-muted">Aucune source détaillée publiée sur cette carte.</p>';
    return `<div class="evidence-list">${rows.map(s=>`<a ${s.url?`href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"`:''}><span class="source-chip ${providerClass(s.source_key)}">${esc(s.source_label||s.source_key||'Source')}</span><b>${esc(s.title||'Signal')}</b><small>${Number.isFinite(Number(s.source_trust))?`fiabilité source ${Math.round(Number(s.source_trust)*100)}/100 · `:''}${esc(s.source_family||'source publique')}</small></a>`).join('')}</div>`;
  }

  function detailDrawer(f,id) {
    const up=favorable(f).slice(0,5), down=contrary(f).slice(0,5), chain=(f?.causal_chain||[]).filter(Boolean);
    const interval=f?.probability?.interval_percent;
    return `<div class="detail-drawer detail-v3" id="detail-${safeId(id)}" hidden>
      <div class="detail-topline"><div><small>POURQUOI MAINTENANT</small><p>${esc(f?.why_now||f?.what_we_know||summary(f))}</p></div><div class="detail-model"><small>ESTIMATION</small><b>${prob(f)}%</b><span>${Array.isArray(interval)?`intervalle ${interval[0]}–${interval[1]}%`:'intervalle non publié'}</span><em>${esc(level(f))} · non calibrée empiriquement</em></div></div>
      ${chain.length?`<div><small>CHAÎNE CAUSALE / PRÉCURSEURS</small><p class="chain">${chain.map(x=>`<span>${esc(x)}</span>`).join('<i>→</i>')}</p></div>`:''}
      <div class="detail-columns"><div><small>CE QUI FERAIT MONTER</small><ul>${up.map(x=>`<li>${esc(x)}</li>`).join('')||'<li>Nouveaux précurseurs indépendants.</li>'}</ul></div><div><small>CE QUI FERAIT BAISSER</small><ul>${down.map(x=>`<li>${esc(x)}</li>`).join('')||'<li>Normalisation durable des signaux.</li>'}</ul></div></div>
      <div><small>CRITÈRE DE RÉFUTATION</small><p>${esc(f?.falsification||'Le résultat annoncé ne se matérialise pas dans la fenêtre définie.')}</p></div>
      <div><small>SOURCES QUI ONT RÉELLEMENT CONTRIBUÉ</small>${evidenceSources(f)}</div>
    </div>`;
  }

  function futureCard(f, idx, featured=false) {
    const p=prob(f), s=solidity(f), h=HORIZONS[tier(f)]||HORIZONS.near, up=favorable(f), down=contrary(f);
    const id=safeId(keyOf(f)||`f-${idx}`); const trend=trajectory(f);
    return `<article class="future-card ${featured?'featured':''}" data-domain="${esc(f.domain||'')}" data-tier="${esc(tier(f))}">
      <div class="future-card-head">
        <span class="domain-pill">${domainIcon(f.domain)}${esc(DOMAIN[f.domain]||f.domain||'Monde')}</span>
        <span class="future-region">${esc(region(f))}</span>
        <span class="solidity-chip" title="Solidité des preuves, distincte de la probabilité">♢ ${s||'—'}/100</span>
      </div>
      <h3>${esc(title(f))}</h3>
      <p class="future-summary">${esc(summary(f))}</p>
      <div class="future-core">
        ${ring(p)}
        <div class="future-facts">
          <span class="window"><b>▣ ${esc(h.short)}</b><small>${esc(dateLabel(f))}</small></span>
          <span class="signal-count up"><b>↗ ${up.length}</b><small>favorables</small></span>
          <span class="signal-count down"><b>↘ ${down.length}</b><small>contraires</small></span>
        </div>
      </div>
      <div class="why-preview"><small>POURQUOI</small><span>${esc(f?.what_we_know||f?.why_now||'Précurseurs convergents détectés.')}</span></div>
      <div class="impact-row">${impactChips(f)}</div>
      <div class="card-footer"><div class="card-sources">${sourceChips(f)}</div><button class="analysis-link" data-detail="${id}">Analyse <span>→</span></button></div>
      <div class="card-trajectory"><span class="${trend==='En hausse'?'up':trend==='En baisse'?'down':''}">${trend}</span><small>${f?.probability_delta_points?`${Number(f.probability_delta_points)>0?'+':''}${Math.round(Number(f.probability_delta_points))} pts depuis le relevé précédent`:f?.fact_status==='conditional_long_range_forecast'?'conditionnel à la persistance des signaux':'trajectoire du cycle actuel'}</small></div>
      ${detailDrawer(f,id)}
    </article>`;
  }

  function pickHighlights(rows) {
    const sorted=[...rows].sort((a,b)=>commercialScore(b)-commercialScore(a));
    const out=[], domains=new Set(), tiers=new Set();
    for(const f of sorted){
      if(out.length>=3) break;
      if(!domains.has(f.domain)){ out.push(f); domains.add(f.domain); tiers.add(tier(f)); }
    }
    for(const f of sorted){
      if(out.length>=3) break;
      if(out.includes(f)) continue;
      if(!tiers.has(tier(f))){ out.push(f); tiers.add(tier(f)); }
    }
    for(const f of sorted){ if(out.length>=3) break; if(!out.includes(f)) out.push(f); }
    return out;
  }

  function horizonRow(key, rows, hiddenHighlighted=0) {
    const meta=HORIZONS[key]; const visible=expandedTier===key?rows:rows.slice(0,3); const canExpand=rows.length>3;
    let cards='';
    if(visible.length) cards=visible.map((f,i)=>futureCard(f,`${key}-${i}`)).join('');
    else cards=`<div class="row-empty-v3"><div><b>${hiddenHighlighted?`${hiddenHighlighted} scénario majeur déjà mis en avant plus haut.`:'Radar actif, rien d’assez solide à publier.'}</b><span>${hiddenHighlighted?'Aucun doublon n’est répété dans cette section.':'ÉVIDENCE laisse cet horizon vide plutôt que d’inventer une carte.'}</span></div></div>`;
    return `<section class="horizon-section" id="horizon-${key}" data-tier="${key}"><div class="horizon-section-head"><span class="horizon-icon">${ICONS[meta.icon]}</span><div><h2>${esc(meta.label)}</h2><p>${esc(meta.sub)}</p></div><strong>${rows.length+hiddenHighlighted}</strong></div><div class="future-grid ${expandedTier===key?'expanded':''}">${cards}</div>${canExpand?`<button class="view-all-v3" data-expand="${key}">${expandedTier===key?'Réduire':'Voir toutes les cartes'} <span>→</span></button>`:''}</section>`;
  }

  function renderBoard(rows, excludeHighlights=true) {
    const groups=Object.fromEntries(HORIZON_ORDER.map(k=>[k,[]]));
    const hidden=Object.fromEntries(HORIZON_ORDER.map(k=>[k,0]));
    rows.forEach(f=>{
      const k=tier(f); if(!groups[k]) groups[k]=[];
      if(excludeHighlights && highlightKeys.has(keyOf(f))) hidden[k]=(hidden[k]||0)+1;
      else groups[k].push(f);
    });
    Object.values(groups).forEach(arr=>arr.sort((a,b)=>commercialScore(b)-commercialScore(a)));
    $('#horizonBoard').innerHTML=HORIZON_ORDER.map(k=>horizonRow(k,groups[k]||[],hidden[k]||0)).join('');
    renderHorizonTabs(rows);
  }

  function renderHorizonTabs(rows) {
    const counts=Object.fromEntries(HORIZON_ORDER.map(k=>[k,rows.filter(f=>tier(f)===k).length]));
    $('#horizonTabs').innerHTML=HORIZON_ORDER.map(k=>`<button data-jump="${k}" class="${counts[k]?'':'empty'}"><span>${esc(HORIZONS[k].short)}</span><b>${counts[k]}</b></button>`).join('');
  }

  function renderSources(data, rows) {
    const catalog=(data?.summary?.source_catalog||[]).filter(Boolean);
    const actualKeys=new Set(rows.flatMap(f=>providers(f).map(s=>s.key)));
    const sorted=[...catalog].sort((a,b)=>Number(actualKeys.has(b.key))-Number(actualKeys.has(a.key)) || Number(b.active)-Number(a.active));
    const visible=sorted.filter(s=>s.active || actualKeys.has(s.key));
    $('#sourceCount').textContent=visible.length||'—';
    $('#sourceGrid').innerHTML=visible.map(s=>{
      const used=actualKeys.has(s.key); const cls=providerClass(s.key);
      return `<div class="source-role"><span class="source-chip ${cls}">${esc(s.label)}</span><p><b>${used?'Contribue aux cartes':'Référence disponible'}</b><small>${esc(s.role||'Source publique')}</small></p><i class="${used?'used':'reference'}">${used?'CALCUL':'RÉF.'}</i></div>`;
    }).join('') || '<span>Sources en consolidation</span>';
    $('#sourceMore').textContent='Une source marquée « RÉF. » n’est pas injectée dans la probabilité affichée.';
  }

  function render(data) {
    snapshot=data;
    const rows=[...(data?.forecasts||[])].filter(f=>!['resolved','invalidated'].includes(f?.status));
    $('#metricForecasts').textContent=formatCompact(rows.length);
    $('#metricSignals').textContent=formatCompact(data?.summary?.signals_considered ?? data?.summary?.evidence_items_considered);
    $('#metricTop').textContent=rows.length?`${Math.max(...rows.map(prob))}%`:'—';
    $('#metricForecastsMeta').textContent=rows.length?`${new Set(rows.map(f=>f.domain)).size} domaines couverts`:'aucun scénario publié';
    $('#metricSignalsMeta').textContent=`${data?.summary?.source_providers ?? 'plusieurs'} sources contributrices`;
    $('#metricTopMeta').textContent='estimation, pas certitude';
    $('#snapshotTime').textContent=`mis à jour ${relative(data?.generated_at)}`;
    $('#eyeSignalCount').textContent=`${formatCompact(data?.summary?.signals_considered)} signaux`;
    $('#eyeHorizonCount').textContent=`${new Set(rows.map(tier)).size} horizons`;
    $('#liveDot').dataset.state='live';

    const highlights=pickHighlights(rows); highlightKeys=new Set(highlights.map(keyOf));
    $('#primaryForecast').innerHTML=highlights.length?highlights.map((f,i)=>futureCard(f,`highlight-${i}`,true)).join(''):'<div class="loading-card"><div><strong>Aucun scénario assez solide.</strong><small>ÉVIDENCE préfère le silence au remplissage artificiel.</small></div></div>';
    renderBoard(rows,true); renderSources(data,rows); wireDynamicEvents();
  }

  async function loadWorldEye() {
    try {
      const r=await fetch(`/api/world-eye?t=${Date.now()}`,{cache:'no-store'});
      if(!r.ok) throw new Error(`HTTP ${r.status}`);
      const eye=await r.json();
      if(!eye?.image_url) throw new Error('image indisponible');
      const img=$('#earthLive');
      img.onload=()=>{ img.hidden=false; $('#earthFallback').hidden=true; };
      img.onerror=()=>{ img.hidden=true; $('#earthFallback').hidden=false; };
      img.src=eye.image_url;
      $('#earthProvider').textContent=eye.provider||'NASA DSCOVR / EPIC';
      const captured=String(eye.captured_at||'').replace('T',' ').replace('Z','');
      $('#earthCaptured').textContent=captured?`acquisition ${captured} UTC`:'dernière acquisition disponible';
      $('#eyeCaption').textContent=eye.caption||'Image réelle de la face éclairée de la Terre.';
    } catch(_error) {
      $('#earthFallback').hidden=false;
      $('#earthCaptured').textContent='flux satellite en reconnexion';
    }
  }

  function wireDynamicEvents() {
    document.querySelectorAll('[data-detail]').forEach(btn=>btn.addEventListener('click',()=>{
      const el=document.getElementById(`detail-${safeId(btn.dataset.detail)}`); if(!el) return;
      el.hidden=!el.hidden; btn.classList.toggle('open',!el.hidden); btn.querySelector('span')?.replaceChildren(document.createTextNode(el.hidden?'→':'↑'));
    }));
    document.querySelectorAll('[data-expand]').forEach(btn=>btn.addEventListener('click',()=>{
      expandedTier=expandedTier===btn.dataset.expand?null:btn.dataset.expand; renderBoard(snapshot?.forecasts||[],true); wireDynamicEvents();
    }));
    document.querySelectorAll('[data-jump]').forEach(btn=>btn.addEventListener('click',()=>{
      const el=document.getElementById(`horizon-${btn.dataset.jump}`); if(!el) return; el.scrollIntoView({behavior:'smooth',block:'start'}); el.classList.add('pulse'); setTimeout(()=>el.classList.remove('pulse'),900);
    }));
  }

  async function load() {
    try {
      let data=null, lastError=null;
      for(const endpoint of SNAPSHOT_ENDPOINTS) {
        try {
          const separator=endpoint.includes('?')?'&':'?';
          const r=await fetch(`${endpoint}${separator}t=${Date.now()}`,{cache:'no-store'});
          if(!r.ok) throw new Error(`HTTP ${r.status}`);
          const candidate=await r.json();
          if(!Array.isArray(candidate?.forecasts)) throw new Error('snapshot invalide');
          data=candidate; break;
        } catch(error) { lastError=error; }
      }
      if(!data) throw lastError||new Error('snapshot indisponible');
      render(data);
    } catch(e) {
      $('#liveDot').dataset.state='error'; $('#snapshotTime').textContent='reconnexion';
      $('#primaryForecast').innerHTML=`<div class="loading-card error"><div><strong>Le champ prédictif se reconnecte.</strong><small>${esc(e.message)}</small></div></div>`;
    }
  }

  $('#searchToggle').addEventListener('click',()=>{const d=$('#searchDrawer'); d.hidden=!d.hidden; if(!d.hidden) $('#searchInput').focus();});
  $('#searchClose').addEventListener('click',()=>$('#searchDrawer').hidden=true);
  $('#searchInput').addEventListener('input',e=>{
    if(!snapshot) return; const q=e.target.value.trim().toLowerCase();
    const rows=(snapshot.forecasts||[]).filter(f=>!q||`${title(f)} ${summary(f)} ${region(f)} ${DOMAIN[f.domain]||''} ${providers(f).map(s=>s.label).join(' ')}`.toLowerCase().includes(q));
    renderBoard(rows,!q); wireDynamicEvents();
  });

  load(); loadWorldEye();
  setInterval(load,5*60*1000);
  setInterval(loadWorldEye,20*60*1000);
})();
