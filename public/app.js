(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const clamp = (v,a,b) => Math.max(a,Math.min(b,Number(v)||0));

  const DOMAIN = {
    natural_hazards:'Risques naturels', weather_climate:'Météo & climat', cyber_technology:'Cyber & espace',
    public_health:'Santé', financial_stress:'Finance', energy:'Énergie', economy_labor:'Économie & emploi',
    supply_fuel:'Commerce & logistique', social_collective_behavior:'Comportements collectifs',
    geopolitics_security:'Géopolitique', regulation_policy:'Décisions & adaptation', transport_mobility:'Transport'
  };
  const HORIZONS = {
    immediate:{label:'Prochaines heures',sub:'Ce qui peut basculer avant 72 heures',order:0},
    near:{label:'Jours & semaines',sub:'Les trajectoires qui peuvent devenir visibles rapidement',order:1},
    medium:{label:'Mois à venir',sub:'Les effets de second ordre qui prennent du temps à se former',order:2},
    long:{label:'1–3 ans',sub:'Les changements structurels qui commencent dans les signaux d’aujourd’hui',order:3},
    strategic:{label:'3–5 ans',sub:'Les futurs stratégiques les plus incertains, mais déjà observables en germe',order:4}
  };

  let allForecasts = [];
  let activeHorizon = 'all';

  const prob = f => Number.isFinite(Number(f?.probability?.percent)) ? Math.round(Number(f.probability.percent)) : Math.round(clamp(f?.probability?.estimate,0,1)*100);
  const solidity = f => Math.round(Number(f?.consolidation?.score ?? f?.confidence ?? 0));
  const formatDate = v => {
    const d = new Date(v); if (Number.isNaN(d.getTime())) return 'date à préciser';
    return new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric'}).format(d);
  };
  const rel = t => {
    if (!t) return '—'; const d = new Date(t), s = Math.max(0,(Date.now()-d)/1000);
    return s<60?'à l’instant':s<3600?`il y a ${Math.floor(s/60)} min`:s<86400?`il y a ${Math.floor(s/3600)} h`:`il y a ${Math.floor(s/86400)} j`;
  };
  const trajectory = f => f?.trajectory === 'building' ? 'En renforcement' : f?.trajectory === 'forming' ? 'En formation' : 'Émergent';
  const tier = f => f?.horizon_tier || f?.time_window?.tier || 'near';
  const region = f => f?.region || f?.geography || 'Monde';
  const sourceLabels = f => (f?.consolidation?.source_providers || []).map(x=>x.label||x.key).filter(Boolean);
  const signalsUp = f => f?.favorable_signals || f?.probability_up_if || [];
  const signalsDown = f => f?.contrary_signals || f?.probability_down_if || [];
  const tags = f => f?.human_needs || [];

  function ring(p, cls='ring') {
    return `<div class="${cls}" style="--p:${clamp(p,0,100)}"><span><strong>${p}</strong><em>%</em></span></div>`;
  }

  function sourceChips(f) {
    const rows = sourceLabels(f).slice(0,4);
    return rows.length ? rows.map(x=>`<span class="source">${esc(x)}</span>`).join('') : '<span class="source">Sources en consolidation</span>';
  }

  function evidenceDetails(f) {
    const up = signalsUp(f).slice(0,4);
    const down = signalsDown(f).slice(0,4);
    const chain = (f.causal_chain||[]).filter(Boolean);
    return `<details class="evidence-details">
      <summary>Voir la trajectoire <span>→</span></summary>
      <div class="evidence-body">
        <div class="detail-lead"><b>Pourquoi maintenant</b><p>${esc(f.why_now || f.what_we_know || 'Les signaux sont en cours de consolidation.')}</p></div>
        ${chain.length ? `<div class="causal"><b>CHAÎNE PROBABLE</b><div>${chain.map((x,i)=>`${i?'<i>→</i>':''}<span>${esc(x)}</span>`).join('')}</div></div>` : ''}
        <div class="signal-columns">
          <div class="signal-box up"><b>↑ CE QUI RENFORCERAIT</b><ul>${up.length?up.map(x=>`<li>${esc(x)}</li>`).join(''):'<li>Aucun signal supplémentaire publié.</li>'}</ul></div>
          <div class="signal-box down"><b>↓ CE QUI FRAGILISERAIT</b><ul>${down.length?down.map(x=>`<li>${esc(x)}</li>`).join(''):'<li>Aucun signal contraire publié.</li>'}</ul></div>
        </div>
        <div class="resolution"><div><small>CONDITION DE MATÉRIALISATION</small><p>${esc(f.resolution_conditions||'La trajectoire doit produire un résultat observable avant la fin de sa fenêtre.')}</p></div><div><small>CONDITION D’ÉCHEC</small><p>${esc(f.falsification||'Le résultat attendu ne se produit pas dans la fenêtre annoncée.')}</p></div></div>
        <div class="sources-line"><small>SOURCES</small>${sourceChips(f)}</div>
      </div>
    </details>`;
  }

  function forecastCard(f) {
    const p = prob(f), c = solidity(f), h = HORIZONS[tier(f)] || HORIZONS.near;
    const up = signalsUp(f).length, down = signalsDown(f).length;
    return `<article class="forecast-card">
      <div class="card-top"><span class="domain"><i></i>${esc(DOMAIN[f.domain]||f.domain||'Monde')}</span><span class="confidence">signal ${c || '—'}/100</span></div>
      <div class="card-main"><div class="card-copy"><div class="where">${esc(region(f))} · ${esc(h.label)}</div><h3>${esc(f.title||f.headline||'Scénario en formation')}</h3><p>${esc(f.summary||f.what_we_know||'')}</p></div>${ring(p,'mini-ring')}</div>
      <div class="forecast-date"><div><small>FENÊTRE</small><strong>${esc(f?.time_window?.human||h.label)}</strong></div><div><small>ÉCHÉANCE MAX.</small><strong>${esc(formatDate(f.target_date||f?.time_window?.end_at))}</strong></div></div>
      <div class="signals-mini"><span class="up">↑ ${up} favorable${up>1?'s':''}</span><span class="down">↓ ${down} contraire${down>1?'s':''}</span><span>${esc(trajectory(f))}</span></div>
      ${tags(f).length?`<div class="tags">${tags(f).slice(0,4).map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:''}
      ${evidenceDetails(f)}
    </article>`;
  }

  function spotlightCard(f) {
    const p = prob(f), c = solidity(f), h = HORIZONS[tier(f)] || HORIZONS.near;
    return `<article class="spot-card"><div class="spot-left"><div class="spot-kicker"><span>${esc(h.label)}</span><i>•</i><span>${esc(region(f))}</span><i>•</i><b>${esc(trajectory(f))}</b></div><h3>${esc(f.title||f.headline)}</h3><p>${esc(f.summary||f.what_we_know||'')}</p><div class="spot-time"><span><small>QUAND</small><strong>${esc(f?.time_window?.human||h.label)}</strong></span><span><small>DATE LIMITE</small><strong>${esc(formatDate(f.target_date||f?.time_window?.end_at))}</strong></span></div><div class="spot-tags">${tags(f).slice(0,5).map(x=>`<span>${esc(x)}</span>`).join('')}</div></div><div class="spot-prob">${ring(p,'hero-ring')}<small>PROBABILITÉ ÉVIDENCE</small><b>signal ${c || '—'}/100</b><div class="spot-sources">${sourceChips(f)}</div></div>${evidenceDetails(f)}</article>`;
  }

  function commercialScore(f) {
    return prob(f) + solidity(f)*.25 + (Number(f?.commercial_priority)||.6)*10 - ((HORIZONS[tier(f)]?.order)||0)*2;
  }

  function populateDomains(rows) {
    const select = $('#domainFilter');
    const current = select.value || 'all';
    const domains = [...new Set(rows.map(f=>f.domain).filter(Boolean))].sort((a,b)=>(DOMAIN[a]||a).localeCompare(DOMAIN[b]||b,'fr'));
    select.innerHTML = '<option value="all">Tous les domaines</option>' + domains.map(d=>`<option value="${esc(d)}">${esc(DOMAIN[d]||d)}</option>`).join('');
    if ([...select.options].some(o=>o.value===current)) select.value=current;
  }

  function renderMetrics(rows) {
    $('#metricForecasts').textContent = rows.length;
    $('#metricImmediate').textContent = rows.filter(f=>tier(f)==='immediate').length;
    $('#metricMedium').textContent = rows.filter(f=>tier(f)==='medium').length;
    $('#metricLong').textContent = rows.filter(f=>['long','strategic'].includes(tier(f))).length;
    $('#metricTop').textContent = rows.length ? `${Math.max(...rows.map(prob))}%` : '—';
  }

  function renderSpotlight(rows) {
    if (!rows.length) { $('#spotlight').innerHTML='<div class="empty"><b>Aucun futur assez solide à mettre en avant.</b><p>ÉVIDENCE préfère laisser l’espace vide plutôt que fabriquer une prédiction.</p></div>'; return; }
    const selected = [...rows].sort((a,b)=>commercialScore(b)-commercialScore(a))[0];
    $('#spotlight').innerHTML = spotlightCard(selected);
  }

  function filteredRows() {
    const q = ($('#search')?.value||'').trim().toLowerCase();
    const domain = $('#domainFilter')?.value || 'all';
    return allForecasts.filter(f => {
      if (activeHorizon !== 'all' && tier(f) !== activeHorizon) return false;
      if (domain !== 'all' && f.domain !== domain) return false;
      if (q) {
        const hay = `${f.title||f.headline||''} ${f.summary||''} ${region(f)} ${DOMAIN[f.domain]||''} ${(tags(f)||[]).join(' ')}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function renderSections() {
    const rows = filteredRows();
    const host = $('#futureSections');
    if (!rows.length) { host.innerHTML='<div class="empty"><b>Aucun scénario ne correspond à ce filtre.</b><p>Élargissez l’horizon ou la recherche.</p></div>'; return; }
    const order = ['immediate','near','medium','long','strategic'];
    host.innerHTML = order.map(key => {
      const meta = HORIZONS[key];
      const sectionRows = rows.filter(f=>tier(f)===key).sort((a,b)=>commercialScore(b)-commercialScore(a));
      if (!sectionRows.length) return '';
      return `<section class="horizon-section"><header><div><span>${esc(meta.label.toUpperCase())}</span><h3>${esc(meta.sub)}</h3></div><b>${sectionRows.length} scénario${sectionRows.length>1?'s':''}</b></header><div class="forecast-grid">${sectionRows.map(forecastCard).join('')}</div></section>`;
    }).join('');
  }

  function render(s) {
    allForecasts = [...(s?.forecasts||[])].filter(f=>f.status!=='resolved' && f.status!=='invalidated');
    populateDomains(allForecasts);
    renderMetrics(allForecasts);
    renderSpotlight(allForecasts);
    renderSections();
    $('#snapshotState').textContent = 'Champ prédictif actif';
    $('#snapshotTime').textContent = `${allForecasts.length} futurs · mis à jour ${rel(s.generated_at)}`;
    $('#live').dataset.state='live';
    $('#liveText').textContent=`${s?.summary?.source_providers ?? 'plusieurs'} sources · live`;
  }

  async function load() {
    try {
      const r = await fetch(`/api/snapshot?t=${Date.now()}`,{cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (!Array.isArray(data?.forecasts)) throw new Error('champ prédictif indisponible');
      render(data);
    } catch (e) {
      $('#live').dataset.state='error'; $('#liveText').textContent='reconnexion';
      $('#snapshotState').textContent='HORIZON se reconnecte'; $('#snapshotTime').textContent=e.message;
      $('#spotlight').innerHTML='<div class="empty"><b>Le radar du futur est momentanément indisponible.</b><p>Le moteur tente de se reconnecter aux sources.</p></div>';
    }
  }

  $('#horizonTabs')?.addEventListener('click', e => {
    const button = e.target.closest('button[data-horizon]'); if (!button) return;
    activeHorizon = button.dataset.horizon; $$('#horizonTabs button').forEach(x=>x.classList.toggle('active',x===button)); renderSections();
  });
  $('#search')?.addEventListener('input',renderSections);
  $('#domainFilter')?.addEventListener('change',renderSections);

  load(); setInterval(load,5*60*1000);
})();
