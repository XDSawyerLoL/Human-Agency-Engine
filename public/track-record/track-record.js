(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const n = v => Number.isFinite(Number(v)) ? Number(v) : 0;
  const pct = v => `${Math.round(n(v) * 100)}%`;
  const date = v => {
    if (!v) return '—';
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('fr-FR',{day:'2-digit',month:'short',year:'numeric'}).format(d);
  };

  function recentRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return '<div class="v5-track-row"><b>Aucun scénario encore enregistré.</b><span>—</span><span>—</span><span>—</span></div>';
    return rows.map(r => `<div class="v5-track-row"><div><b>${esc(r.title || r.scenario_id || 'Scénario')}</b><small>${esc(r.domain || 'Monde')} · ${esc(r.horizon_tier || 'horizon variable')}</small></div><span class="pct">${pct(r.first_probability)}</span><span class="pct">${pct(r.last_probability)}</span><span>${esc(date(r.target_at))}</span></div>`).join('');
  }

  function buckets(rows) {
    const max = Math.max(1, ...(rows || []).map(x => n(x.active)));
    return (rows || []).map(b => `<div class="v5-bucket"><span>${esc(b.label)}</span><i style="--w:${Math.round(n(b.active)/max*100)}%"></i><b>${n(b.active)}</b></div>`).join('');
  }

  async function init() {
    try {
      const r = await fetch('/api/track-record',{cache:'no-store'});
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      $('#trackedScenarios').textContent = n(d.tracked_scenarios).toLocaleString('fr-FR');
      $('#historyPoints').textContent = n(d.probability_history_points).toLocaleString('fr-FR');
      $('#revisedScenarios').textContent = n(d.scenarios_with_revisions).toLocaleString('fr-FR');
      $('#resolvedScenarios').textContent = n(d.resolved_scenarios).toLocaleString('fr-FR');
      $('#trackNote').textContent = d.note || 'Collecte historique en cours.';
      if (d.brier_score !== null && d.brier_score !== undefined) {
        $('#brierScore').textContent = Number(d.brier_score).toFixed(3);
        $('#brierMeta').textContent = 'plus bas = meilleur';
      } else {
        $('#brierScore').textContent = '—';
        $('#brierMeta').textContent = d.calibration_ready ? 'calcul à finaliser' : 'en collecte';
      }
      $('#trackTable').innerHTML = `<div class="v5-track-row header"><span>SCÉNARIO</span><span>PROBA INITIALE</span><span>DERNIÈRE</span><span>ÉCHÉANCE</span></div>${recentRows(d.recent)}`;
      $('#probabilityBuckets').innerHTML = buckets(d.buckets);
      $('#calibrationText').textContent = d.calibration_ready
        ? `Le corpus contient ${n(d.resolved_scenarios)} scénarios résolus. La prochaine étape est le calcul automatique de la calibration et du Brier Score par domaine et horizon.`
        : `Il faut encore accumuler des prédictions arrivées à échéance avant de pouvoir vérifier si, par exemple, nos estimations à 70 % se réalisent réellement environ 70 % du temps.`;
      $('#storageWarning').textContent = d.storage_mode === 'mysql'
        ? 'Historique persistant actif : les révisions survivent aux redéploiements Hostinger.'
        : 'Historique actuellement en mémoire : un redémarrage Hostinger peut remettre le corpus à zéro. Pour une preuve historique durable, il faudra connecter le MySQL inclus à l’hébergement.';
    } catch (error) {
      $('#trackNote').textContent = `Track Record indisponible : ${error.message}`;
      $('#storageWarning').textContent = 'Le moteur prédictif peut continuer à fonctionner même si la page de preuve historique est momentanément indisponible.';
    }
  }
  init();
})();