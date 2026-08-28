(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#039;'}[c]));
  const n = v => Number.isFinite(Number(v)) ? Number(v) : 0;
  const pctProb = v => `${Math.round(n(v) * 100)}%`;
  const DOMAIN={energy:'Énergie',geopolitics_security:'Géopolitique',cyber_technology:'Technologie & cyber',public_health:'Santé',financial_stress:'Finance',economy_labor:'Économie & emploi',weather_climate:'Climat',natural_hazards:'Risques naturels',social_collective_behavior:'Société',supply_fuel:'Commerce & logistique',regulation_policy:'Régulation',transport_mobility:'Transport'};
  const HORIZON={immediate:'≤72 h',near:'Jours–semaines',medium:'Mois',long:'1–3 ans',strategic:'3–5 ans',deep:'5 ans +'};
  const date = v => { if (!v) return '—'; const d = new Date(v); return Number.isNaN(d.getTime()) ? '—' : new Intl.DateTimeFormat('fr-FR',{day:'2-digit',month:'short',year:'numeric'}).format(d); };

  function verdictRows(rows, resolutionRecent=[]) {
    const state=new Map((resolutionRecent||[]).map(x=>[x.scenario_key,x]));
    const resolved=(rows||[]).filter(r=>['resolved','auto_resolved'].includes(state.get(r.scenario_key)?.resolution_status));
    if (!resolved.length) return '<div class="v5-track-row"><b>Aucun verdict résolu récent.</b><span>—</span><span>—</span><span>—</span></div>';
    return resolved.slice(0,12).map(r => { const s=state.get(r.scenario_key)||{}; return `<div class="v5-track-row"><div><b>${esc(r.title || r.scenario_id || 'Scénario')}</b><small>${esc(DOMAIN[r.domain] || r.domain || 'Monde')} · ${esc(HORIZON[r.horizon_tier] || r.horizon_tier || 'horizon variable')} · ${esc((s.resolution_status||'résolu').replaceAll('_',' '))}</small></div><span class="pct">${pctProb(r.first_probability)}</span><span class="pct">${pctProb(r.last_probability)}</span><span>${esc(date(r.target_at))}</span></div>`; }).join('');
  }

  function queueRows(rows, resolutionRecent=[]) {
    if (!Array.isArray(rows) || !rows.length) return '<div class="v5-track-row"><b>Aucune résolution en attente.</b><span>—</span><span>—</span><span>—</span></div>';
    const state=new Map((resolutionRecent||[]).map(x=>[x.scenario_key,x]));
    return `<div class="v5-track-row header"><span>SCÉNARIO</span><span>PROBA INITIALE</span><span>ÉTAT</span><span>ÉCHÉANCE</span></div>` + rows.map(r => {
      const s=state.get(r.scenario_key); const label=s?.resolution_status||'pending';
      return `<div class="v5-track-row"><div><b>${esc(r.title || r.scenario_id || 'Scénario')}</b><small>${esc(s?.note || 'Vérité terrain nécessaire')}</small></div><span class="pct">${pctProb(r.first_probability)}</span><span>${esc(label.replaceAll('_',' '))}</span><span>${esc(date(r.target_at))}</span></div>`;
    }).join('');
  }

  function buckets(rows) {
    const active=(rows||[]).filter(x=>n(x.n)>0);
    if(!active.length) return '<div class="v5-note">Pas encore assez de résolutions pour dessiner la courbe.</div>';
    return active.map(b=>{ const observed=n(b.observed_frequency); const mean=n(b.mean_probability); return `<div class="v8-bucket"><small>${esc(b.label)}</small><div class="v8-bucket-track"><i style="--w:${Math.round(observed*100)}%"></i></div><strong>${Math.round(mean*100)} → ${Math.round(observed*100)}%</strong></div>`; }).join('');
  }

  function segmentRows(rows,type) {
    if(!Array.isArray(rows)||!rows.length) return '<div class="v5-note">Aucun segment résolu.</div>';
    return rows.map(x=>{ const label=type==='domain'?(DOMAIN[x.key]||x.key):(HORIZON[x.key]||x.key); const state=x.ready?'ready':'collecting'; return `<div class="v8-segment"><b>${esc(label)}</b><small>${n(x.n)} cas</small><span>Brier ${x.brier===null?'—':Number(x.brier).toFixed(3)}</span><span class="${state}">${x.ready?'mesurable':'collecte'}</span></div>`; }).join('');
  }

  function resolutionSummary(states={}) {
    const order=[['resolved','résolus'],['auto_resolved','auto-résolus'],['suggested_positive','à confirmer'],['needs_review','à vérifier']];
    const rows=order.filter(([key])=>n(states[key])>0);
    return rows.length?rows.map(([key,label])=>`<span>${esc(label)} <b>${n(states[key])}</b></span>`).join(''):'<span>aucune échéance traitée <b>0</b></span>';
  }

  function setStatus(id,text,kind='') { const el=$(id); if(!el)return; el.textContent=text; el.className=`v8-status ${kind}`.trim(); }

  async function init() {
    try {
      const r = await fetch('/api/track-record',{cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const c=d.calibration||{}; const g=c.global||{}; const resolution=d.resolution||{};
      $('#trackedScenarios').textContent = n(d.tracked_scenarios).toLocaleString('fr-FR');
      $('#historyPoints').textContent = n(d.probability_history_points).toLocaleString('fr-FR');
      $('#revisedScenarios').textContent = n(d.scenarios_with_revisions).toLocaleString('fr-FR');
      $('#resolvedScenarios').textContent = n(c.scorable_resolutions).toLocaleString('fr-FR');
      $('#trackNote').textContent = c.calibration_ready ? `${n(c.scorable_resolutions)} résolutions binaires entrent maintenant dans le score public.` : `${n(c.scorable_resolutions)} résolutions binaires scorables. Le seuil public de calibration est ${n(c.minimum_global_samples)||30}.`;
      $('#brierScore').textContent = g.brier === null || g.brier === undefined ? '—' : Number(g.brier).toFixed(3);
      $('#brierMeta').textContent = g.brier === null || g.brier === undefined ? 'en collecte' : 'plus bas = meilleur';
      $('#logLoss').textContent = g.log_loss === null || g.log_loss === undefined ? '—' : Number(g.log_loss).toFixed(3);
      $('#eceScore').textContent = g.ece === null || g.ece === undefined ? '—' : Number(g.ece).toFixed(3);
      $('#brierSkill').textContent = g.brier_skill_score === null || g.brier_skill_score === undefined ? '—' : `${g.brier_skill_score>=0?'+':''}${(Number(g.brier_skill_score)*100).toFixed(1)}%`;
      $('#hitRate').textContent = d.hit_rate === null || d.hit_rate === undefined ? '—' : `${Number(d.hit_rate).toFixed(1)}%`;
      $('#trackTable').innerHTML = `<div class="v5-track-row header"><span>SCÉNARIO RÉSOLU</span><span>PROBA INITIALE</span><span>DERNIÈRE</span><span>ÉCHÉANCE</span></div>${verdictRows(d.recent,resolution.recent)}`;
      $('#resolutionQueue').innerHTML = queueRows(d.resolution_queue,resolution.recent);
      $('#resolutionSummary').innerHTML = resolutionSummary(resolution.states);
      $('#probabilityBuckets').innerHTML = buckets(c.buckets);
      $('#calibrationDomains').innerHTML = segmentRows(c.by_domain,'domain');
      $('#calibrationHorizons').innerHTML = segmentRows(c.by_horizon,'horizon');
      $('#calibrationText').textContent = c.calibration_ready ? `Calibration active sur ${n(c.scorable_resolutions)} scénarios binaires résolus. ECE mesure l’écart entre probabilité annoncée et fréquence observée ; le skill compare le Brier à une baseline de fréquence.` : `Le moteur calcule déjà les scores, mais ne les utilise pas pour modifier les probabilités publiques avant ${n(c.minimum_global_samples)||30} résolutions binaires vérifiées.`;
      const persistent=d.storage_mode==='mysql'&&d.persistent_learning;
      $('#storageWarning').textContent = persistent ? 'Historique persistant actif : probabilités, métadonnées, preuves et résolutions survivent aux redéploiements Hostinger.' : 'Apprentissage en mémoire : le moteur fonctionne, mais le corpus peut être perdu à un redémarrage tant que MySQL Hostinger n’est pas raccordé.';
      setStatus('#storageState',persistent?'MYSQL · PERSISTANT':'MÉMOIRE · À RACCORDER',persistent?'ok':'warn');
      setStatus('#resolutionState','RESOLUTION ENGINE · ACTIF','ok');
      setStatus('#calibrationState',c.calibration_ready?'CALIBRATION · ACTIVE':`CALIBRATION · ${n(c.scorable_resolutions)}/${n(c.minimum_global_samples)||30}`,c.calibration_ready?'ok':'warn');
    } catch (error) {
      $('#trackNote').textContent = `Track Record indisponible : ${error.message}`;
      $('#storageWarning').textContent = 'Le moteur prédictif continue de fonctionner, mais la couche de preuve historique n’a pas répondu.';
      setStatus('#storageState','ERREUR TRACK RECORD','warn');
    }
  }
  init();
})();