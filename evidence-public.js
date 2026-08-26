(() => {
  "use strict";

  const REPO = "XDSawyerLoL/Human-Agency-Engine";
  const SNAPSHOT_URL = `https://raw.githubusercontent.com/${REPO}/evidence-live-data/evidence-live.json`;
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[c]);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));

  const DOMAIN_LABELS = {
    weather_climate:"Météo & climat",natural_hazards:"Risques naturels",transport_mobility:"Transport & mobilité",
    social_collective_behavior:"Comportements collectifs",supply_fuel:"Approvisionnement",energy:"Énergie",
    media_attention:"Attention médiatique",geopolitics_security:"Géopolitique",economy_labor:"Économie & travail",
    public_health:"Santé publique",cyber_technology:"Cyber & technologie",regulation_policy:"Régulation",
    financial_stress:"Stress financier",personal_context:"Contexte personnel"
  };

  function probability(forecast){
    const p = Number(forecast?.probability?.percent);
    return Number.isFinite(p) ? Math.round(clamp(p,0,100)) : Math.round(clamp(Number(forecast?.probability?.estimate)*100,0,100));
  }
  function interval(forecast){
    const v=forecast?.probability?.interval_percent;
    return Array.isArray(v)&&v.length>=2?[Math.round(Number(v[0])||0),Math.round(Number(v[1])||0)]:[0,0];
  }
  function origin(f){return f?.fact_status==="forecast_from_confirmed_event"?"Précurseur confirmé":"Signal émergent"}
  function trajectory(f){return ({building:"En renforcement",forming:"En formation",fragile:"Fragile"})[f?.trajectory]||"En observation"}
  function deltaData(f){
    const d=Number(f?.probability_delta_points),dir=f?.probability_direction;
    if(!Number.isFinite(d)||dir==="new")return{label:"Nouveau scénario",cls:"stable"};
    if(dir==="rising")return{label:`+${d.toFixed(1)} pts`,cls:""};
    if(dir==="falling")return{label:`${d.toFixed(1)} pts`,cls:"down"};
    return{label:`${d>=0?"+":""}${d.toFixed(1)} pt`,cls:"stable"};
  }
  function relativeTime(value){
    if(!value)return"—";const d=new Date(value);if(Number.isNaN(d.getTime()))return"—";
    const s=Math.max(0,Math.round((Date.now()-d.getTime())/1000));
    if(s<60)return"à l’instant";if(s<3600)return`il y a ${Math.floor(s/60)} min`;if(s<86400)return`il y a ${Math.floor(s/3600)} h`;return`il y a ${Math.floor(s/86400)} j`;
  }
  function list(items, fallback){
    const a=(items||[]).filter(Boolean);if(!a.length)return`<li>${esc(fallback)}</li>`;return a.map(x=>`<li>${esc(x)}</li>`).join("");
  }
  function sourceChips(consolidation){
    const sources=consolidation?.source_families||[];
    if(!sources.length)return`<span class="source-chip">Sources en consolidation</span>`;
    return sources.map(s=>`<span class="source-chip" title="Poids de confiance ${Math.round((Number(s.trust)||0)*100)}/100">${esc(s.label||s.key)}</span>`).join("");
  }
  function dimensions(consolidation){
    return (consolidation?.dimensions||[]).map(d=>{
      const score=Math.round(clamp(d.score,0,100));
      return `<div class="dimension"><label>${esc(d.label)}</label><b>${score}</b><div class="dimension-track"><i style="width:${score}%"></i></div></div>`;
    }).join("")||`<div class="dimension"><label>Diagnostic en cours</label><b>—</b><div class="dimension-track"><i style="width:0"></i></div></div>`;
  }
  function sparkline(forecast){
    const hist=(forecast?.probability_history||[]).map(p=>Number(p?.percent)).filter(Number.isFinite).slice(-12);
    const values=hist.length?hist:[probability(forecast)];
    if(values.length===1)values.unshift(values[0]);
    const w=130,h=38,pad=3,min=Math.min(...values,0),max=Math.max(...values,100),range=Math.max(1,max-min);
    const points=values.map((v,i)=>[pad+(i/(values.length-1))*(w-pad*2),h-pad-((v-min)/range)*(h-pad*2)]);
    const pts=points.map(([x,y])=>`${x},${y}`).join(" ");
    const [lx,ly]=points.at(-1);
    return `<svg viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/><circle cx="${lx}" cy="${ly}" r="2.6" fill="currentColor"/></svg>`;
  }
  function trendText(f){
    const hist=(f?.probability_history||[]).map(p=>Number(p?.percent)).filter(Number.isFinite).slice(-6);
    return hist.length?hist.map(v=>Math.round(v)).join(" → ")+" %":probability(f)+" %";
  }
  function chainHtml(f){
    const steps=(f?.causal_chain||[]).filter(Boolean);
    if(!steps.length)return`<span>Chaîne encore incomplète</span>`;
    return steps.map((s,i)=>`${i?"<i>→</i>":""}<span>${esc(s)}</span>`).join("");
  }
  function competitionHtml(f){
    const c=f?.consolidation?.scenario_competition;
    let outcomes=c?.outcomes||[];
    if(outcomes.length<2){const p=probability(f);outcomes=[{label:f?.headline||"Matérialisation",percent:p},{label:"Non-matérialisation dans la fenêtre",percent:100-p}]}
    const a=outcomes[0],b=outcomes[1],pa=clamp(a.percent,0,100),pb=clamp(b.percent,0,100);
    return `<div class="competition"><div class="competition-labels"><div><strong>${Math.round(pa)}%</strong><small>${esc(a.label)}</small></div><div><strong>${Math.round(pb)}%</strong><small>${esc(b.label)}</small></div></div><div class="competition-bar"><i style="width:${pa}%"></i><i style="width:${pb}%"></i></div></div>`;
  }
  function divergenceHtml(f){
    const d=f?.consolidation?.divergence||{};const delta=Number(d.delta_points);
    const signed=Number.isFinite(delta)?`${delta>0?"+":""}${delta.toFixed(1)} pts`:"—";
    const external=Boolean(d.external_consensus_available);
    return `<div class="divergence"><small>${external?"ÉCART AU CONSENSUS EXTERNE":"ÉCART AU PRIOR DU MODÈLE"}</small><strong>${signed}</strong><p>${esc(d.reference_label||"Prior interne du modèle")} : ${d.reference_percent??"—"}% · ${esc(d.label||"référence de comparaison")}. ${external?"":"Aucun consensus externe n’est mélangé sans autorisation explicite."}</p></div>`;
  }
  function primaryHtml(f){
    const p=probability(f),[lo,hi]=interval(f),d=deltaData(f),c=f?.consolidation||{},score=Number(c.score),level=c.level||"en cours";
    return `<article class="forecast-hero">
      <div class="forecast-main">
        <div class="forecast-copy">
          <div class="forecast-meta"><span class="pill hot">${esc(trajectory(f))}</span><span class="pill">${esc(origin(f))}</span><span class="pill">${esc(DOMAIN_LABELS[f.domain]||f.domain_label||f.domain||"Monde")}</span></div>
          <h3>${esc(f.headline||f.outcome||"Scénario en formation")}</h3>
          <p class="why">${esc(f.why_now||"Le moteur consolide encore l’explication de ce scénario.")}</p>
          <div class="window-box"><small>FENÊTRE DE MATÉRIALISATION</small><strong>${esc(f?.time_window?.human||"Fenêtre encore indéterminée")}</strong></div>
          <div class="trend-line">${sparkline(f)}<div class="trend-copy"><b>${esc(trendText(f))}</b><small>évolution de l’estimation au fil des cycles</small></div></div>
        </div>
        <div class="probability-panel">
          <div class="probability-ring" style="--p:${p}"><span><strong>${p}</strong><em>%</em></span></div>
          <small>ESTIMATION ÉVIDENCE</small><p>Intervalle ${lo}–${hi} %</p><span class="delta ${d.cls}">${esc(d.label)}</span>
        </div>
        <aside class="consolidation-panel">
          <div class="consolidation-head"><div><small>CONSOLIDATION</small><strong>${esc(level)}</strong></div><div class="consolidation-score">${Number.isFinite(score)?Math.round(score):"—"}<small>/100</small></div></div>
          <div class="source-chips">${sourceChips(c)}</div><div class="dimension-list">${dimensions(c)}</div>
          <p class="probability-note">Le ${p}% vient du modèle Évidence. Le score de consolidation mesure la solidité des entrées : <strong>ce n’est pas une seconde probabilité.</strong></p>
        </aside>
      </div>
      <div class="forecast-explain">
        <div class="evidence-story">
          <div class="subhead">COMMENT LE SCÉNARIO SE CONSTRUIT</div><div class="causal-chain">${chainHtml(f)}</div>
          <div class="evidence-columns"><div class="evidence-box good"><strong>CE QUI LE RENFORCE</strong><ul>${list([...(c.strengths||[]),...(f.probability_up_if||[])].slice(0,5),"Aucun renforcement supplémentaire publié.")}</ul></div><div class="evidence-box bad"><strong>CE QUI LE FRAGILISE</strong><ul>${list([...(c.weaknesses||[]),...(f.probability_down_if||[])].slice(0,5),"Aucune faiblesse supplémentaire publiée.")}</ul></div></div>
        </div>
        <aside class="scenario-panel"><div class="subhead">DEUX ISSUES POUR CETTE FENÊTRE</div>${competitionHtml(f)}${divergenceHtml(f)}<div class="falsification"><small>CONDITION D’INVALIDATION</small><p>${esc(f.falsification||"La règle d’invalidation n’est pas encore publiée.")}</p></div></aside>
      </div>
    </article>`;
  }
  function cardHtml(f){
    const p=probability(f),d=deltaData(f),c=f?.consolidation||{};
    return `<article class="forecast-card"><div><div class="meta">${esc(origin(f))} · ${esc(DOMAIN_LABELS[f.domain]||f.domain_label||f.domain||"Monde")}</div><h3>${esc(f.headline||f.outcome||"Scénario")}</h3><div class="card-window">${esc(f?.time_window?.human||"Fenêtre indéterminée")} · ${esc(d.label)}</div></div><div class="mini-ring" style="--p:${p}"><strong>${p}%</strong></div><div class="card-footer"><span>${esc((c.source_families||[]).slice(0,3).map(s=>s.label||s.key).join(" · ")||"Sources en consolidation")}</span><b>Consolidation ${c.score??"—"}/100 · ${esc(c.level||"en cours")}</b></div><details><summary>Voir pourquoi cette prévision existe ↓</summary><div>${esc(f.why_now||"Explication non publiée.")}<br><br><b>Invalidation :</b> ${esc(f.falsification||"non publiée")}</div></details></article>`;
  }
  function render(snapshot){
    const forecasts=[...(snapshot?.forecasts||[])].sort((a,b)=>probability(b)-probability(a));
    $("#metricEvidence").textContent=snapshot?.summary?.evidence_items_considered??"—";
    $("#metricForecasts").textContent=forecasts.length;
    $("#metricSources").textContent=snapshot?.summary?.source_families??"—";
    $("#metricRising").textContent=forecasts.filter(f=>f?.probability_direction==="rising").length;
    $("#metricTop").textContent=forecasts.length?`${probability(forecasts[0])}%`:"—";
    $("#snapshotState").textContent=snapshot?.engine?.includes("v0.3")?"Évidence multi-source actif":"Évidence prédictif actif";
    $("#snapshotTime").textContent=snapshot?.generated_at?`snapshot ${relativeTime(snapshot.generated_at)}`:"snapshot sans horodatage";
    $("#liveBadge").dataset.state="live";$("#liveText").textContent="flux actif";
    if(!forecasts.length){$("#primaryForecast").innerHTML=`<div class="empty-state"><strong>Aucun scénario assez solide à publier.</strong><p>Le moteur fonctionne, mais il refuse de fabriquer une prévision uniquement pour remplir le tableau de bord. Les prochains cycles réévalueront les signaux.</p></div>`;$("#forecastGrid").innerHTML="";return;}
    $("#primaryForecast").innerHTML=primaryHtml(forecasts[0]);
    $("#forecastGrid").innerHTML=forecasts.slice(1).map(cardHtml).join("");
  }
  async function load(){
    try{const r=await fetch(`${SNAPSHOT_URL}?t=${Date.now()}`,{cache:"no-store"});if(!r.ok)throw new Error(`HTTP ${r.status}`);const snapshot=await r.json();if(!Array.isArray(snapshot?.forecasts))throw new Error("snapshot prédictif pas encore publié");render(snapshot)}catch(err){$("#liveBadge").dataset.state="error";$("#liveText").textContent="flux en transition";$("#snapshotState").textContent="Publication prédictive en transition";$("#snapshotTime").textContent=String(err.message||err);$("#primaryForecast").innerHTML=`<div class="empty-state"><strong>Le nouveau flux prédictif n’est pas encore disponible.</strong><p>Le cockpit n’affiche pas l’ancien radar de problèmes comme s’il s’agissait de prédictions. Il attend le snapshot Évidence v2/v0.3.</p></div>`;}
  }
  load();setInterval(load,5*60*1000);
})();
