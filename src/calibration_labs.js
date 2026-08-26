const UA = 'Evidence-World-Eye/1.0 (+calibration-lab)';
const memo = new Map();

async function fetchJson(url, timeoutMs=12_000) {
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), timeoutMs);
  try {
    const r = await fetch(url,{signal:controller.signal,headers:{'user-agent':UA,accept:'application/json'}});
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally { clearTimeout(timer); }
}

function brier3(pred, outcome) {
  const y = outcome === 'home' ? [1,0,0] : outcome === 'draw' ? [0,1,0] : [0,0,1];
  return ((pred[0]-y[0])**2 + (pred[1]-y[1])**2 + (pred[2]-y[2])**2) / 3;
}

function outcomeOf(m) {
  const h = Number(m.home_score), a = Number(m.away_score);
  if(!Number.isFinite(h)||!Number.isFinite(a)) return null;
  return h>a?'home':h===a?'draw':'away';
}

export async function sportsCalibrationLab() {
  const cached = memo.get('sports');
  if(cached && Date.now()-cached.at < 6*3600_000) return {...cached.value,cached:true};
  const base='https://raw.githubusercontent.com/statsbomb/open-data/master/data';
  const competitions=await fetchJson(`${base}/competitions.json`);
  const candidates=(competitions||[])
    .filter(x=>String(x.competition_gender||'').toLowerCase()==='male')
    .sort((a,b)=>String(b.season_name||'').localeCompare(String(a.season_name||'')));
  let chosen=null, matches=null;
  for(const c of candidates.slice(0,24)){
    try{
      const rows=await fetchJson(`${base}/matches/${c.competition_id}/${c.season_id}.json`,8_000);
      if(Array.isArray(rows)&&rows.length>=20){chosen=c;matches=rows;break;}
    }catch{}
  }
  if(!chosen||!matches) throw new Error('Aucune compétition StatsBomb exploitable actuellement.');
  const ordered=matches.filter(m=>outcomeOf(m)).sort((a,b)=>Date.parse(a.match_date||0)-Date.parse(b.match_date||0));
  const cut=Math.max(10,Math.floor(ordered.length*.7));
  const train=ordered.slice(0,cut), test=ordered.slice(cut);
  const counts={home:0,draw:0,away:0};
  train.forEach(m=>counts[outcomeOf(m)]++);
  const total=Math.max(1,train.length);
  const prior=[counts.home/total,counts.draw/total,counts.away/total];
  const scores=test.map(m=>brier3(prior,outcomeOf(m)));
  const brier=scores.length?scores.reduce((a,b)=>a+b,0)/scores.length:null;
  const actual={home:0,draw:0,away:0}; test.forEach(m=>actual[outcomeOf(m)]++);
  const value={
    status:'ok',
    provider:'StatsBomb Open Data',
    purpose:'calibration_r_and_d',
    competition:chosen.competition_name,
    season:chosen.season_name,
    training_matches:train.length,
    test_matches:test.length,
    baseline_probabilities:{home:Math.round(prior[0]*1000)/10,draw:Math.round(prior[1]*1000)/10,away:Math.round(prior[2]*1000)/10},
    test_outcomes:actual,
    multiclass_brier:brier===null?null:Math.round(brier*10000)/10000,
    interpretation:'Baseline volontairement simple. Le but est de disposer d’un terrain à résolution rapide pour tester calibration, ensembles et mises à jour probabilistes.',
    transfer_warning:'Une bonne calibration sportive ne prouve pas une capacité prédictive générale ; elle sert à valider les mécanismes mathématiques.'
  };
  memo.set('sports',{at:Date.now(),value});
  return {...value,cached:false};
}

export function benchmarkRoadmap() {
  return {
    futureeval:{status:'adapter_ready_not_submitting',reason:'Participation/automatisation externe à activer uniquement avec autorisation et identifiants appropriés.'},
    sports:{status:'active',provider:'StatsBomb Open Data'},
    weather:{status:'shadow_mode',reason:'Calibration météo historique à brancher sur une source autorisée pour usage commercial avant publication de scores.'},
    markets:{status:'reference_only',reason:'Consensus externe conservé séparé de la probabilité ÉVIDENCE.'}
  };
}
