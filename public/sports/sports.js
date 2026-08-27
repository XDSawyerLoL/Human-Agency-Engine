(()=>{
  'use strict';
  const $=s=>document.querySelector(s);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const country=$('#sportsCountry'),league=$('#sportsLeague'),season=$('#sportsSeason'),run=$('#sportsRun'),status=$('#sportsStatus');
  let catalog=null;
  const pct=v=>Number.isFinite(Number(v))?`${Math.round(Number(v)*100)}%`:'—';
  const date=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?'—':new Intl.DateTimeFormat('fr-FR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}).format(d)};
  const currentCountry=()=>catalog?.countries?.find(x=>x.country===country.value)||null;
  const currentLeague=()=>currentCountry()?.leagues?.find(x=>x.name===league.value)||null;
  function setStatus(text,sub=''){status.innerHTML=`<span class="pulse"></span><strong>${esc(text)}</strong><small>${esc(sub)}</small>`;}
  function fillCountries(){country.innerHTML=(catalog.countries||[]).map(x=>`<option>${esc(x.country)}</option>`).join('');const preferred=[...country.options].find(o=>/England/i.test(o.value));if(preferred)country.value=preferred.value;fillLeagues();}
  function fillLeagues(){const c=currentCountry();league.innerHTML=(c?.leagues||[]).map(x=>`<option>${esc(x.name)}</option>`).join('');const preferred=[...league.options].find(o=>/Premier League/i.test(o.value));if(preferred)league.value=preferred.value;fillSeasons();}
  function fillSeasons(){const l=currentLeague();season.innerHTML=(l?.seasons||[]).map(x=>`<option value="${esc(x.competition_id)}:${esc(x.season_id)}">${esc(x.season_name)}</option>`).join('');}
  function grade(brier){if(!Number.isFinite(Number(brier)))return ['—',''];if(brier<=.19)return ['TRÈS SOLIDE','grade-good'];if(brier<=.225)return ['SOLIDE','grade-good'];if(brier<=.26)return ['À AFFINER','grade-mid'];return ['FRAGILE','grade-low'];}
  function render(data){
    const h=data.historical||{},u=data.upcoming||{},metrics=$('#sportsMetrics').querySelectorAll('article');
    metrics[0].querySelector('strong').textContent=h.matches??'—';metrics[1].querySelector('strong').textContent=Number.isFinite(Number(h.multiclass_brier))?Number(h.multiclass_brier).toFixed(4):'—';metrics[2].querySelector('strong').textContent=pct(h.top_pick_accuracy);metrics[3].querySelector('strong').textContent=u.fixtures?.length??0;
    const [g,cls]=grade(h.multiclass_brier);const ge=$('#calibrationGrade');ge.textContent=g;ge.className=cls;
    $('#calibrationChart').innerHTML=(h.calibration_buckets||[]).length?(h.calibration_buckets||[]).map(b=>`<div class="cal-row"><label>${esc(b.label)} · n=${b.n}</label><div class="cal-track" style="--pred:${Math.round((b.mean_confidence||0)*100)}%;--obs:${Math.round((b.observed_accuracy||0)*100)}%"><i></i><b></b></div><strong>${pct(b.mean_confidence)}</strong><em>${pct(b.observed_accuracy)}</em></div>`).join(''):'<div class="sports-empty">Pas assez de matchs pour tracer la calibration.</div>';
    $('#modelSummary').innerHTML=`<p>${esc(data.model?.name||'Providence Sports')}</p><div class="model-features">${(data.model?.features||[]).map(x=>`<span>${esc(x)}</span>`).join('')}</div><p>Entraînement chronologique : <strong>${data.model?.trained_only_on_prior_matches?'oui':'non'}</strong>. Aucun résultat futur n’est utilisé pour prédire le passé.</p>`;
    $('#teamRatings').innerHTML=(data.teams?.top_ratings||[]).slice(0,10).map((t,i)=>`<div class="rating-row"><strong>${String(i+1).padStart(2,'0')} · ${esc(t.key)}</strong><span>${t.rating}</span></div>`).join('');
    $('#fixtureProvider').textContent=`${u.provider||'Source'} · ${u.coverage||'—'}`;
    $('#upcomingFixtures').innerHTML=(u.fixtures||[]).length?(u.fixtures||[]).map(f=>`<article class="fixture-card"><small>${esc(date(f.utc_date))} · ${esc(f.competition||data.competition?.name||'')}</small><h3>${esc(f.home)} <span>vs</span> ${esc(f.away)}</h3><div class="fixture-probs"><div><small>1</small><strong>${f.probabilities?.home_percent??'—'}%</strong></div><div><small>N</small><strong>${f.probabilities?.draw_percent??'—'}%</strong></div><div><small>2</small><strong>${f.probabilities?.away_percent??'—'}%</strong></div></div><div class="pick">Providence → ${esc(f.model_pick||'—')} · confiance ${f.model_confidence_percent??'—'}%</div></article>`).join(''):'<div class="sports-empty">Aucun prochain match retourné par la source gratuite pour cette ligue.</div>';
    $('#historyMeta').textContent=`${h.test_matches||0} matchs de test`;
    $('#historyRows').innerHTML=(h.recent_test_matches||[]).map(r=>`<tr><td>${esc(r.date||'—')}</td><td>${esc(r.home)} — ${esc(r.away)}</td><td class="${r.correct?'hit':'miss'}">${esc(r.prediction_label||r.prediction)}</td><td>1 ${pct(r.probabilities?.home)} · N ${pct(r.probabilities?.draw)} · 2 ${pct(r.probabilities?.away)}</td><td>${esc(r.outcome==='home'?'1':r.outcome==='draw'?'N':'2')}</td><td>${Number(r.brier).toFixed(3)}</td></tr>`).join('')||'<tr><td colspan="6">Aucun historique de test.</td></tr>';
    setStatus(`${data.competition?.country||''} · ${data.competition?.name||''} · ${data.competition?.season||''}`,`Historique ${h.provider||'StatsBomb'} · prochains matchs ${u.provider||'indisponibles'}`);
  }
  async function analyze(){
    const raw=season.value.split(':');if(raw.length<2)return;run.disabled=true;setStatus('Providence rejoue la saison…','Calcul chronologique de la calibration');
    try{const params=new URLSearchParams({country:country.value,competition_id:raw[0],season_id:raw[1],league:league.value});const r=await fetch(`/api/sports/league?${params}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);render(await r.json());}
    catch(e){status.innerHTML=`<div class="sports-error">Impossible de charger cette ligue : ${esc(e.message)}</div>`;}
    finally{run.disabled=false;}
  }
  country.addEventListener('change',()=>{fillLeagues();analyze();});league.addEventListener('change',()=>{fillSeasons();analyze();});season.addEventListener('change',analyze);run.addEventListener('click',analyze);
  (async()=>{try{const r=await fetch('/api/sports/catalog',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);catalog=await r.json();fillCountries();await analyze();}catch(e){status.innerHTML=`<div class="sports-error">Catalogue sportif indisponible : ${esc(e.message)}</div>`;}})();
})();