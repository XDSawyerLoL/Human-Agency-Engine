(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const icons = { gdelt:'◎', pubmed:'✚', arxiv:'⌁', polymarket:'◌', trends:'↗', fred:'▥', metaculus:'◇', windy:'≈' };
  const date = v => { const d=new Date(v); return Number.isNaN(d.getTime())?'—':new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'short',year:'numeric'}).format(d); };

  function moduleCard(m) {
    const core = Boolean(m.core_input);
    const themes = Array.isArray(m.themes) && m.themes.length
      ? `<select data-theme="${esc(m.key)}" aria-label="Thème ${esc(m.label)}">${m.themes.map(t => `<option value="${esc(t.key)}">${esc(t.label)}</option>`).join('')}</select>` : '';
    const verb = m.key==='gdelt'?'Lancer l’analyse':m.key==='metaculus'?'Voir les questions':m.key==='windy'?'Ouvrir Weather Eye':'Synchroniser';
    return `<article class="v5-module ${core ? 'core' : 'reference'}"><div class="v5-module-top"><span class="v5-module-icon">${icons[m.key] || '◎'}</span><span class="v5-status ${core ? '' : 'reference'}">${core ? 'MOTEUR' : 'SIGNAL'}</span></div><h3>${esc(m.label)}</h3><p>${esc(m.description)}</p><span class="v5-tag ${core ? 'core' : 'ref'}">${esc(m.status || 'actif')}</span><div class="v5-module-foot">${themes}<button class="v5-btn" data-run="${esc(m.key)}">${verb}</button></div></article>`;
  }

  function forecastCard(f) {
    const p = Math.round(Number(f?.probability?.percent ?? (Number(f?.probability?.estimate || 0) * 100)));
    const horizon = f?.time_window?.human || f?.horizon_label || f?.horizon_tier || 'horizon variable';
    return `<article class="v5-result-card"><small>SCÉNARIO ÉVIDENCE · ${esc(horizon)}</small><h4>${esc(f?.title || f?.headline || 'Scénario')}</h4><p>${esc(f?.summary || f?.why_now || '')}</p><div class="prob">${Number.isFinite(p) ? p : '—'}%</div></article>`;
  }

  function projectionMeta(projection){
    if(!projection)return 'ForecastAPI : non disponible';
    if(projection.error)return `ForecastAPI : ${projection.error}`;
    const rows=Array.isArray(projection.forecast)?projection.forecast:[];
    if(!rows.length)return 'ForecastAPI : aucune trajectoire retournée';
    const preview=rows.slice(0,3).map(x=>{const v=x.value??x.forecast??x.yhat??'—';return `${x.date||x.ds||'future'} → ${v}`}).join(' · ');
    return `ForecastAPI : ${preview}`;
  }

  function itemRow(item, moduleKey) {
    const title = item.title || item.question || item.query || item.label || item.series || 'Résultat';
    let meta = '';
    if (moduleKey === 'polymarket') meta = `${item.probability ?? '—'}% marché · volume ${Number(item.volume || 0).toLocaleString('fr-FR')} · ${date(item.end_date)}`;
    else if (moduleKey === 'trends') meta = item.traffic || 'tendance émergente';
    else if (moduleKey === 'fred') meta = `${item.series || ''} · observé ${item.latest ?? '—'} le ${item.date || '—'} · ${projectionMeta(item.projection)}`;
    else if (['metaculus','windy'].includes(moduleKey)) meta = `${item.probability ?? '—'}% · ${item.region || 'Monde'} · échéance ${date(item.target_date)}`;
    else meta = [item.topic, item.domain, item.date || item.seen_at].filter(Boolean).join(' · ');
    const inner = `<b>${esc(title)}</b><small>${esc(meta)}</small>`;
    return item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${inner}<span>↗</span></a>` : `<div>${inner}<span></span></div>`;
  }

  function renderLinks(data){
    const links=Array.isArray(data.links)?data.links:[];
    return links.length?`<div class="v5-quicklinks">${links.map(x=>`<a class="v5-btn secondary" href="${esc(x.url)}" target="${String(x.url).startsWith('/')?'_self':'_blank'}" rel="noopener noreferrer">${esc(x.label)} ↗</a>`).join('')}</div>`:'';
  }
  function renderMap(data){
    return data.map_embed_url?`<div class="v5-module-map"><iframe title="Carte météo Windy" src="${esc(data.map_embed_url)}" loading="lazy" referrerpolicy="no-referrer"></iframe></div>`:'';
  }
  function renderMeta(data){
    if(!data.meta || typeof data.meta!=='object')return '';
    const entries=Object.entries(data.meta).filter(([,v])=>['string','number','boolean'].includes(typeof v));
    return entries.length?`<div class="v5-module-meta">${entries.map(([k,v])=>`<span><small>${esc(k.replaceAll('_',' ').toUpperCase())}</small><b>${esc(v)}</b></span>`).join('')}</div>`:'';
  }

  function renderResult(data) {
    $('#resultTitle').textContent = data.label || 'Résultat du module';
    $('#resultMeta').textContent = data.theme_label ? `Thème : ${data.theme_label}` : `Dernière exécution : ${new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'})}`;
    const forecasts = Array.isArray(data.forecasts) ? data.forecasts : [];
    const items = Array.isArray(data.items) ? data.items : [];
    const blocks = [renderMeta(data),renderMap(data),renderLinks(data)].filter(Boolean);
    if (forecasts.length) blocks.push(`<div class="v5-result-grid">${forecasts.slice(0,12).map(forecastCard).join('')}</div>`);
    if (items.length) blocks.push(`<div class="v5-list">${items.slice(0,40).map(x => itemRow(x, data.key)).join('')}</div>`);
    if (data.notice) blocks.push(`<div class="v5-note">${esc(data.notice)}</div>`);
    if (!blocks.length) blocks.push('<div class="v5-note">Le module a répondu mais aucun élément exploitable n’est disponible sur ce cycle.</div>');
    $('#moduleOutput').innerHTML = `<div class="v5-output-head"><h3>${esc(data.label || data.key || 'Module')}</h3><span>${data.cached ? 'résultat en cache' : 'analyse fraîche'}</span></div>${blocks.join('')}`;
    document.getElementById('results')?.scrollIntoView({behavior:'smooth',block:'start'});
  }

  async function runModule(key, button) {
    const old = button.textContent; button.disabled = true; button.textContent = 'Analyse…';
    $('#moduleOutput').innerHTML = '<div class="v5-note">Connexion à la source et préparation des résultats…</div>';
    try {
      const theme = document.querySelector(`[data-theme="${CSS.escape(key)}"]`)?.value || '';
      const r = await fetch(`/api/modules/${encodeURIComponent(key)}/run`, {method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({theme})});
      const data = await r.json();
      if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);
      renderResult(data);
    } catch (error) {
      $('#resultTitle').textContent = 'Module indisponible'; $('#resultMeta').textContent = 'Diagnostic du connecteur';
      $('#moduleOutput').innerHTML = `<div class="v5-note"><b>${esc(key)}</b> : ${esc(error.message)}.</div>`;
    } finally { button.disabled = false; button.textContent = old; }
  }

  async function runSports(button){
    const old=button.textContent; button.disabled=true; button.textContent='Backtest…';
    $('#moduleOutput').innerHTML='<div class="v5-note">Calcul de la baseline sportive et du score de calibration…</div>';
    try{
      const r=await fetch('/api/calibration/sports',{cache:'no-store'}); const data=await r.json();
      if(!r.ok)throw new Error(data?.error||`HTTP ${r.status}`);
      renderResult({
        key:'sports',label:'Sports Calibration Lab',
        meta:{competition:data.competition||'—',saison:data.season||'—',entrainement:data.training_matches??'—',test:data.test_matches??'—',brier_multiclasses:data.multiclass_brier??'—'},
        items:[],notice:data.interpretation||'Backtest sportif terminé.'
      });
    }catch(error){
      renderResult({key:'sports',label:'Sports Calibration Lab',items:[],notice:`Backtest indisponible : ${error.message}`});
    }finally{button.disabled=false;button.textContent=old;}
  }

  async function init() {
    try {
      const r = await fetch('/api/modules', {cache:'no-store'}); if (!r.ok) throw new Error(`HTTP ${r.status}`); const data = await r.json();
      const modules = Array.isArray(data.modules) ? data.modules : [];
      $('#moduleGrid').innerHTML = modules.map(moduleCard).join('') || '<div class="v5-output">Aucun module publié.</div>';
      document.querySelectorAll('[data-run]').forEach(btn => btn.addEventListener('click', () => runModule(btn.dataset.run, btn)));
      document.querySelectorAll('[data-sports-calibration]').forEach(btn=>btn.addEventListener('click',()=>runSports(btn)));
    } catch (error) { $('#moduleGrid').innerHTML = `<div class="v5-output"><div class="v5-note">Impossible de charger les modules : ${esc(error.message)}</div></div>`; }
  }
  init();
})();