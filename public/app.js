(() => {
  'use strict';

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, Number(v) || 0));
  const page = document.body.dataset.page || 'home';
  const SNAPSHOT_ENDPOINTS = ['/api/snapshot', './data/evidence-live.json'];
  const HORIZON_ORDER = ['immediate', 'near', 'medium', 'long', 'strategic', 'deep'];

  const DOMAIN = {
    natural_hazards:'Risques naturels', weather_climate:'Climat & météo', cyber_technology:'Cyber & technologie',
    public_health:'Santé', financial_stress:'Finance', energy:'Énergie', economy_labor:'Économie & emploi',
    supply_fuel:'Commerce & logistique', social_collective_behavior:'Comportements collectifs',
    geopolitics_security:'Géopolitique', regulation_policy:'Décisions & régulation', transport_mobility:'Transport'
  };
  const HORIZONS = {
    immediate:{label:'≤ 72 heures',sub:'Ce qui peut basculer presque immédiatement.',order:0},
    near:{label:'Jours à semaines',sub:'Conséquences déjà en formation.',order:1},
    medium:{label:'Mois à venir',sub:'Dynamiques susceptibles de devenir visibles dans les prochains mois.',order:2},
    long:{label:'1 à 3 ans',sub:'Transformations structurelles à moyen terme.',order:3},
    strategic:{label:'3 à 5 ans',sub:'Trajectoires stratégiques si les signaux persistent.',order:4},
    deep:{label:'5 ans et +',sub:'Scénarios conditionnels à très long terme.',order:5}
  };

  let snapshot = null;

  const prob = f => Number.isFinite(Number(f?.probability?.percent))
    ? Math.round(Number(f.probability.percent))
    : Math.round(clamp(f?.probability?.estimate, 0, 1) * 100);
  const solidity = f => Math.round(Number(f?.consolidation?.score ?? f?.confidence ?? 0));
  const tier = f => f?.horizon_tier || f?.time_window?.tier || 'near';
  const region = f => f?.region || f?.geography || 'Monde';
  const title = f => f?.title || f?.headline || f?.outcome || 'Scénario en formation';
  const summary = f => f?.summary || f?.public_summary || f?.what_we_know || f?.why_now || '';
  const favorable = f => (f?.favorable_signals || f?.probability_up_if || []).filter(Boolean);
  const contrary = f => (f?.contrary_signals || f?.probability_down_if || []).filter(Boolean);
  const impacts = f => (f?.human_needs || []).filter(Boolean).slice(0, 5);
  const providers = f => (f?.consolidation?.source_providers || []).filter(Boolean);
  const keyOf = f => f?.scenario_key || f?.id || title(f);
  const safeId = v => String(v || 'x').replace(/[^a-zA-Z0-9_-]/g, '-');
  const commercialScore = f => prob(f) + solidity(f) * .28 + (Number(f?.commercial_priority) || .55) * 10 - (HORIZONS[tier(f)]?.order || 0) * 1.2;

  const formatCompact = n => {
    n = Number(n);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('fr-FR', { notation:n >= 10000 ? 'compact' : 'standard', maximumFractionDigits:1 }).format(n);
  };

  const relative = t => {
    if (!t) return '—';
    const d = new Date(t);
    if (Number.isNaN(d.getTime())) return '—';
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return 'à l’instant';
    if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
    return `il y a ${Math.floor(s / 86400)} j`;
  };

  const dateLabel = f => {
    const raw = f?.target_date || f?.time_window?.end_at;
    if (!raw) return HORIZONS[tier(f)]?.label || '—';
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return HORIZONS[tier(f)]?.label || '—';
    return new Intl.DateTimeFormat('fr-FR', { day:'numeric', month:'short', year:'numeric' }).format(d);
  };

  function providerClass(key = '') {
    const k = String(key).toLowerCase();
    if (k.includes('gdelt')) return 'gdelt';
    if (k.includes('who')) return 'who';
    if (k.includes('nasa')) return 'nasa';
    if (k.includes('usgs')) return 'usgs';
    if (k.includes('noaa')) return 'noaa';
    if (k.includes('copernicus')) return 'copernicus';
    if (k.includes('fred')) return 'fred';
    if (k.includes('forecast')) return 'forecast';
    if (k.includes('metaculus')) return 'metaculus';
    return 'generic';
  }

  function probabilityTone(p) {
    if (p >= 70) return 'high';
    if (p >= 45) return 'mid';
    return 'low';
  }

  function sourceChips(f, limit = 5) {
    const rows = providers(f).slice(0, limit);
    return rows.length
      ? rows.map(s => `<span class="v4-source ${providerClass(s.key)}" title="${esc(s.role || 'Source contributrice')}">${esc(s.label || s.key)}</span>`).join('')
      : '<span class="v4-source generic">ÉVIDENCE</span>';
  }

  function impactChips(f) {
    const rows = impacts(f);
    return rows.length ? rows.map(x => `<span>${esc(x)}</span>`).join('') : '<span>Impact à préciser</span>';
  }

  function evidenceList(f) {
    const rows = (f?.evidence || []).slice(0, 10);
    if (!rows.length) return '<p class="v4-muted">Aucune preuve détaillée publiée pour cette carte.</p>';
    return `<div class="v4-evidence-list">${rows.map(s => {
      const body = `<span class="v4-source ${providerClass(s.source_key)}">${esc(s.source_label || s.source_key || 'Source')}</span><div><b>${esc(s.title || 'Signal')}</b><small>${Number.isFinite(Number(s.source_trust)) ? `Fiabilité source ${Math.round(Number(s.source_trust) * 100)}/100 · ` : ''}${esc(s.source_family || 'source publique')}</small></div>`;
      return s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${body}</a>` : `<div class="evidence-static">${body}</div>`;
    }).join('')}</div>`;
  }

  function detailPanel(f, id) {
    const up = favorable(f).slice(0, 6);
    const down = contrary(f).slice(0, 6);
    const chain = (f?.causal_chain || []).filter(Boolean);
    const interval = f?.probability?.interval_percent;
    return `<div class="v4-detail" id="detail-${id}" hidden>
      <div class="v4-detail-grid">
        <section><small>POURQUOI MAINTENANT</small><p>${esc(f?.why_now || f?.what_we_know || summary(f))}</p></section>
        <section class="v4-estimate"><small>ESTIMATION ÉVIDENCE</small><strong>${prob(f)}%</strong><p>${Array.isArray(interval) ? `Intervalle ${interval[0]}–${interval[1]}%` : 'Intervalle non publié'}</p><em>Probabilité de modèle · non calibrée empiriquement</em></section>
      </div>
      ${chain.length ? `<section><small>CHAÎNE CAUSALE / PRÉCURSEURS</small><div class="v4-chain">${chain.map(x => `<span>${esc(x)}</span>`).join('<i>→</i>')}</div></section>` : ''}
      <div class="v4-detail-grid two">
        <section><small>CE QUI FERAIT MONTER</small><ul>${up.map(x => `<li>${esc(x)}</li>`).join('') || '<li>Nouveaux précurseurs indépendants.</li>'}</ul></section>
        <section><small>CE QUI FERAIT BAISSER</small><ul>${down.map(x => `<li>${esc(x)}</li>`).join('') || '<li>Normalisation durable des signaux.</li>'}</ul></section>
      </div>
      <section><small>CRITÈRE DE RÉFUTATION</small><p>${esc(f?.falsification || 'Le résultat annoncé ne se matérialise pas dans la fenêtre définie.')}</p></section>
      <section><small>SOURCES QUI ONT RÉELLEMENT CONTRIBUÉ</small>${evidenceList(f)}</section>
    </div>`;
  }

  function card(f, { featured = false, compact = false } = {}) {
    const p = prob(f);
    const s = solidity(f);
    const id = safeId(keyOf(f));
    return `<article class="v4-card ${featured ? 'featured' : ''} ${compact ? 'compact' : ''}" data-domain="${esc(f.domain || '')}" data-tier="${esc(tier(f))}">
      <div class="v4-card-top">
        <span class="v4-domain">${esc(DOMAIN[f.domain] || f.domain || 'Monde')}</span>
        <span class="v4-region">${esc(region(f))}</span>
        <span class="v4-solidity" title="Solidité des preuves, distincte de la probabilité">preuves ${s || '—'}/100</span>
      </div>
      <h3>${esc(title(f))}</h3>
      <p class="v4-summary">${esc(summary(f))}</p>
      <div class="v4-card-main">
        <div class="v4-ring ${probabilityTone(p)}" style="--p:${clamp(p, 0, 100)}"><span>${p}<small>%</small></span><em>probabilité</em></div>
        <div class="v4-facts">
          <div><small>HORIZON</small><b>${esc(HORIZONS[tier(f)]?.label || tier(f))}</b><span>${esc(dateLabel(f))}</span></div>
          <div class="up"><small>SIGNAUX +</small><b>↗ ${favorable(f).length}</b><span>favorables</span></div>
          <div class="down"><small>SIGNAUX −</small><b>↘ ${contrary(f).length}</b><span>contraires</span></div>
        </div>
      </div>
      <div class="v4-why"><small>POURQUOI CETTE PRÉVISION</small><p>${esc(f?.what_we_know || f?.why_now || 'Précurseurs convergents détectés.')}</p></div>
      <div class="v4-impacts">${impactChips(f)}</div>
      <div class="v4-card-bottom"><div class="v4-sources">${sourceChips(f)}</div><button class="v4-analysis" data-detail="${id}">Voir l’analyse <span>→</span></button></div>
      ${detailPanel(f, id)}
    </article>`;
  }

  function wireDetails(root = document) {
    $$('[data-detail]', root).forEach(btn => {
      btn.onclick = () => {
        const el = $(`#detail-${safeId(btn.dataset.detail)}`);
        if (!el) return;
        el.hidden = !el.hidden;
        btn.classList.toggle('open', !el.hidden);
        const span = $('span', btn);
        if (span) span.textContent = el.hidden ? '→' : '↑';
      };
    });
  }

  function pickHighlights(rows) {
    const sorted = [...rows].sort((a, b) => commercialScore(b) - commercialScore(a));
    const out = [], domains = new Set();
    for (const f of sorted) {
      if (out.length >= 3) break;
      if (!domains.has(f.domain)) { out.push(f); domains.add(f.domain); }
    }
    for (const f of sorted) {
      if (out.length >= 3) break;
      if (!out.includes(f)) out.push(f);
    }
    return out;
  }

  function activeRows(data) {
    return [...(data?.forecasts || [])].filter(f => !['resolved', 'invalidated'].includes(f?.status));
  }

  function renderGlobalMetrics(data, rows) {
    $$('[data-metric="forecasts"]').forEach(el => el.textContent = formatCompact(rows.length));
    $$('[data-metric="signals"]').forEach(el => el.textContent = formatCompact(data?.summary?.signals_considered ?? data?.summary?.evidence_items_considered));
    $$('[data-metric="domains"]').forEach(el => el.textContent = formatCompact(new Set(rows.map(f => f.domain)).size));
    $$('[data-metric="sources"]').forEach(el => el.textContent = formatCompact(data?.summary?.source_providers));
    $$('[data-snapshot-time]').forEach(el => el.textContent = `Mis à jour ${relative(data?.generated_at)}`);
  }

  function renderHome(data, rows) {
    renderGlobalMetrics(data, rows);
    const target = $('#homeHighlights');
    if (target) {
      const highlights = pickHighlights(rows);
      target.innerHTML = highlights.length ? highlights.map((f, i) => card(f, { featured:i === 0 })).join('') : '<div class="v4-empty">Aucun scénario assez solide à publier.</div>';
      wireDetails(target);
    }
    const eyeSignal = $('#eyeSignalCount');
    if (eyeSignal) eyeSignal.textContent = `${formatCompact(data?.summary?.signals_considered)} signaux observés`;
    const eyeHorizon = $('#eyeHorizonCount');
    if (eyeHorizon) eyeHorizon.textContent = `${new Set(rows.map(tier)).size} horizons actifs`;
  }

  function renderPredictionGrid(rows) {
    const target = $('#predictionGrid');
    if (!target) return;
    target.innerHTML = rows.length ? rows.map(f => card(f)).join('') : '<div class="v4-empty">Aucune prévision ne correspond à ce filtre.</div>';
    wireDetails(target);
  }

  function setupPredictionFilters(rows) {
    const search = $('#predictionSearch');
    const domain = $('#predictionDomain');
    const horizon = $('#predictionHorizon');
    if (!search || !domain || !horizon) return renderPredictionGrid(rows);

    const domains = [...new Set(rows.map(f => f.domain).filter(Boolean))].sort((a, b) => String(DOMAIN[a] || a).localeCompare(String(DOMAIN[b] || b), 'fr'));
    domain.innerHTML = '<option value="">Tous les domaines</option>' + domains.map(d => `<option value="${esc(d)}">${esc(DOMAIN[d] || d)}</option>`).join('');
    horizon.innerHTML = '<option value="">Tous les horizons</option>' + HORIZON_ORDER.map(h => `<option value="${h}">${esc(HORIZONS[h].label)}</option>`).join('');

    const apply = () => {
      const q = search.value.trim().toLowerCase();
      const d = domain.value;
      const h = horizon.value;
      const filtered = rows.filter(f => {
        const text = `${title(f)} ${summary(f)} ${region(f)} ${DOMAIN[f.domain] || ''} ${providers(f).map(s => s.label).join(' ')}`.toLowerCase();
        return (!q || text.includes(q)) && (!d || f.domain === d) && (!h || tier(f) === h);
      });
      const count = $('#predictionCount');
      if (count) count.textContent = `${filtered.length} scénario${filtered.length > 1 ? 's' : ''}`;
      renderPredictionGrid(filtered.sort((a, b) => commercialScore(b) - commercialScore(a)));
    };
    search.addEventListener('input', apply);
    domain.addEventListener('change', apply);
    horizon.addEventListener('change', apply);
    apply();
  }

  function renderHorizons(data, rows) {
    renderGlobalMetrics(data, rows);
    const target = $('#horizonBoard');
    if (!target) return;
    target.innerHTML = HORIZON_ORDER.map(h => {
      const group = rows.filter(f => tier(f) === h).sort((a, b) => commercialScore(b) - commercialScore(a));
      return `<section class="v4-horizon-section" id="${h}">
        <header><div><span>${esc(HORIZONS[h].label)}</span><h2>${esc(HORIZONS[h].sub)}</h2></div><strong>${group.length}</strong></header>
        <div class="v4-grid">${group.length ? group.map(f => card(f, { compact:true })).join('') : '<div class="v4-empty">Radar actif : rien d’assez solide à publier sur cet horizon.</div>'}</div>
      </section>`;
    }).join('');
    wireDetails(target);
  }

  function renderSources(data, rows) {
    renderGlobalMetrics(data, rows);
    const target = $('#sourceCatalogGrid');
    if (!target) return;
    const actual = new Set(rows.flatMap(f => providers(f).map(s => s.key)));
    const catalog = (data?.summary?.source_catalog || []).filter(Boolean);
    target.innerHTML = catalog.map(s => {
      const used = actual.has(s.key);
      return `<article class="v4-source-card ${used ? 'used' : 'reference'}">
        <div class="v4-source-card-head"><span class="v4-source ${providerClass(s.key)}">${esc(s.label || s.key)}</span><b>${used ? 'CALCUL' : 'RÉFÉRENCE'}</b></div>
        <h3>${esc(s.role || 'Source publique')}</h3>
        <p>${used ? 'Cette source contribue réellement à au moins une prévision actuellement publiée.' : 'Cette source est disponible comme contexte ou référence, mais n’entre pas dans la probabilité actuellement affichée.'}</p>
        <small>${esc(s.key)}</small>
      </article>`;
    }).join('') || '<div class="v4-empty">Catalogue de sources en initialisation.</div>';

    const contract = $('#engineContract');
    if (contract) {
      const c = data?.contract || {};
      contract.innerHTML = `
        <div><b>${c.current_event_is_not_forecast === true ? '✓' : '—'}</b><span>Un événement présent n’est pas présenté comme une prévision.</span></div>
        <div><b>${c.falsification_required === true ? '✓' : '—'}</b><span>Chaque scénario doit pouvoir être réfuté.</span></div>
        <div><b>${c.duplicate_public_scenarios_allowed === false ? '✓' : '—'}</b><span>Les doublons publics ne doivent pas gonfler artificiellement la probabilité.</span></div>
        <div><b>${c.five_plus_year_scenarios_are_conditional === true ? '✓' : '—'}</b><span>Les scénarios à 5+ ans sont explicitement conditionnels.</span></div>`;
    }
  }

  async function loadWorldEye() {
    const img = $('#earthLive');
    if (!img) return;
    try {
      const r = await fetch(`/api/world-eye?t=${Date.now()}`, { cache:'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const eye = await r.json();
      if (!eye?.image_url) throw new Error('Image indisponible');
      img.onload = () => { img.hidden = false; $('#earthFallback')?.setAttribute('hidden', ''); };
      img.onerror = () => { img.hidden = true; $('#earthFallback')?.removeAttribute('hidden'); };
      img.src = eye.image_url;
      const provider = $('#earthProvider');
      if (provider) provider.textContent = eye.provider || 'NASA DSCOVR / EPIC';
      const captured = $('#earthCaptured');
      if (captured) captured.textContent = eye.captured_at ? `Acquisition ${String(eye.captured_at).replace('T',' ').replace('Z','')} UTC` : 'Dernière acquisition disponible';
    } catch (_error) {
      $('#earthFallback')?.removeAttribute('hidden');
      const captured = $('#earthCaptured');
      if (captured) captured.textContent = 'Flux satellite en reconnexion';
    }
  }

  async function fetchSnapshot() {
    let lastError;
    for (const endpoint of SNAPSHOT_ENDPOINTS) {
      try {
        const r = await fetch(`${endpoint}${endpoint.includes('?') ? '&' : '?'}t=${Date.now()}`, { cache:'no-store' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        if (!Array.isArray(data?.forecasts)) throw new Error('Snapshot invalide');
        return data;
      } catch (error) { lastError = error; }
    }
    throw lastError || new Error('Snapshot indisponible');
  }

  function showLoadError(error) {
    const target = $('#homeHighlights') || $('#predictionGrid') || $('#horizonBoard') || $('#sourceCatalogGrid');
    if (target) target.innerHTML = `<div class="v4-empty error"><b>Le champ prédictif se reconnecte.</b><span>${esc(error.message)}</span></div>`;
  }

  async function load() {
    try {
      snapshot = await fetchSnapshot();
      const rows = activeRows(snapshot);
      if (page === 'home') renderHome(snapshot, rows);
      if (page === 'predictions') { renderGlobalMetrics(snapshot, rows); setupPredictionFilters(rows); }
      if (page === 'horizons') renderHorizons(snapshot, rows);
      if (page === 'sources') renderSources(snapshot, rows);
    } catch (error) { showLoadError(error); }
  }

  load();
  loadWorldEye();
  setInterval(load, 5 * 60 * 1000);
  setInterval(loadWorldEye, 20 * 60 * 1000);
})();