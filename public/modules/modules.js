(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const icons = { gdelt:'◎', pubmed:'✚', arxiv:'⌁', polymarket:'◌', trends:'↗', fred:'▥', metaculus:'◇', windy:'≈' };

  function moduleCard(m) {
    const core = Boolean(m.core_input);
    const themes = Array.isArray(m.themes) && m.themes.length
      ? `<select data-theme="${esc(m.key)}" aria-label="Thème ${esc(m.label)}">${m.themes.map(t => `<option value="${esc(t.key)}">${esc(t.label)}</option>`).join('')}</select>`
      : '';
    const action = m.actionable
      ? `<button class="v5-btn" data-run="${esc(m.key)}">${m.key === 'gdelt' ? 'Lancer l’analyse' : 'Synchroniser'}</button>`
      : `<a class="v5-btn secondary" href="/sources/">Voir le rôle</a>`;
    return `<article class="v5-module ${core ? 'core' : 'reference'}">
      <div class="v5-module-top"><span class="v5-module-icon">${icons[m.key] || '◎'}</span><span class="v5-status ${core ? '' : 'reference'}">${core ? 'MOTEUR' : 'RÉFÉRENCE'}</span></div>
      <h3>${esc(m.label)}</h3>
      <p>${esc(m.description)}</p>
      <span class="v5-tag ${core ? 'core' : 'ref'}">${esc(m.status || (core ? 'actif' : 'référence'))}</span>
      <div class="v5-module-foot">${themes}${action}</div>
    </article>`;
  }

  function forecastCard(f) {
    const p = Math.round(Number(f?.probability?.percent ?? (Number(f?.probability?.estimate || 0) * 100)));
    const horizon = f?.time_window?.human || f?.horizon_label || f?.horizon_tier || 'horizon variable';
    return `<article class="v5-result-card"><small>SCÉNARIO ÉVIDENCE · ${esc(horizon)}</small><h4>${esc(f?.title || f?.headline || 'Scénario')}</h4><p>${esc(f?.summary || f?.why_now || '')}</p><div class="prob">${Number.isFinite(p) ? p : '—'}%</div></article>`;
  }

  function itemRow(item, moduleKey) {
    let title = item.title || item.question || item.query || item.label || item.series || 'Résultat';
    let meta = '';
    if (moduleKey === 'polymarket') meta = `${item.probability ?? '—'}% marché · volume ${Number(item.volume || 0).toLocaleString('fr-FR')}`;
    else if (moduleKey === 'trends') meta = item.traffic || 'tendance émergente';
    else if (moduleKey === 'fred') meta = `${item.series || ''} · ${item.latest ?? '—'} · ${item.date || ''}`;
    else meta = [item.topic, item.domain, item.date || item.seen_at].filter(Boolean).join(' · ');
    const inner = `<b>${esc(title)}</b><small>${esc(meta)}</small>`;
    return item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${inner}<span>↗</span></a>` : `<div>${inner}<span></span></div>`;
  }

  function renderResult(data) {
    $('#resultTitle').textContent = data.label || 'Résultat du module';
    $('#resultMeta').textContent = data.theme_label ? `Thème : ${data.theme_label}` : `Dernière exécution : ${new Date().toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit'})}`;
    const forecasts = Array.isArray(data.forecasts) ? data.forecasts : [];
    const items = Array.isArray(data.items) ? data.items : [];
    const blocks = [];
    if (forecasts.length) blocks.push(`<div class="v5-result-grid">${forecasts.slice(0,8).map(forecastCard).join('')}</div>`);
    if (items.length) blocks.push(`<div class="v5-list">${items.slice(0,20).map(x => itemRow(x, data.key)).join('')}</div>`);
    if (data.notice) blocks.push(`<div class="v5-note">${esc(data.notice)}</div>`);
    if (!blocks.length) blocks.push('<div class="v5-note">Le module n’a rien remonté d’assez exploitable sur ce cycle. ÉVIDENCE préfère un résultat vide à une fausse prédiction.</div>');
    $('#moduleOutput').innerHTML = `<div class="v5-output-head"><h3>${esc(data.label || data.key || 'Module')}</h3><span>${data.cached ? 'résultat en cache' : 'analyse fraîche'}</span></div>${blocks.join('')}`;
    document.getElementById('results')?.scrollIntoView({behavior:'smooth',block:'start'});
  }

  async function runModule(key, button) {
    const old = button.textContent;
    button.disabled = true;
    button.textContent = 'Analyse…';
    $('#moduleOutput').innerHTML = '<div class="v5-note">Le module interroge ses sources et prépare les résultats. Cela peut prendre quelques secondes.</div>';
    try {
      const theme = document.querySelector(`[data-theme="${CSS.escape(key)}"]`)?.value || '';
      const r = await fetch(`/api/modules/${encodeURIComponent(key)}/run`, {
        method:'POST',
        headers:{'content-type':'application/json'},
        body:JSON.stringify({theme})
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);
      renderResult(data);
    } catch (error) {
      $('#resultTitle').textContent = 'Module indisponible';
      $('#resultMeta').textContent = 'La source distante n’a pas répondu correctement.';
      $('#moduleOutput').innerHTML = `<div class="v5-note">${esc(error.message)}. Le moteur principal continue de fonctionner indépendamment de ce module.</div>`;
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  }

  async function init() {
    try {
      const r = await fetch('/api/modules', {cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const modules = Array.isArray(data.modules) ? data.modules : [];
      $('#moduleGrid').innerHTML = modules.map(moduleCard).join('') || '<div class="v5-output">Aucun module publié.</div>';
      document.querySelectorAll('[data-run]').forEach(btn => btn.addEventListener('click', () => runModule(btn.dataset.run, btn)));
    } catch (error) {
      $('#moduleGrid').innerHTML = `<div class="v5-output"><div class="v5-note">Impossible de charger le catalogue : ${esc(error.message)}</div></div>`;
    }
  }
  init();
})();