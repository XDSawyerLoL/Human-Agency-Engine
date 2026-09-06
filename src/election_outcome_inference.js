const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=1)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const norm=v=>String(v??'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const canon=v=>norm(v).replace(/\b(mme|m|monsieur|madame)\b/g,'').trim();

function matchupKey(names=[]){return names.map(canon).sort().join('|');}
function firstRoundMap(model){return new Map((model?.first_round?.candidates||[]).map(x=>[canon(x.candidate),x]));}
function headToHeadMap(model){const map=new Map();for(const row of model?.second_round||[])map.set(matchupKey(row.matchup||[]),row);return map;}

function conservativeSyntheticRunoff(a,b,first){
  const A=first.get(canon(a)),B=first.get(canon(b));const pa=Number(A?.poll_average),pb=Number(B?.poll_average);
  if(!Number.isFinite(pa)||!Number.isFinite(pb))return [{candidate:a,percent:50},{candidate:b,percent:50}];
  const diff=pa-pb;
  // Le premier tour ne prédit pas directement les reports du second tour : on n'autorise qu'un faible déplacement autour de 50/50.
  const lean=Math.tanh(diff/12)*10;
  return [{candidate:a,percent:round(clamp(50+lean,38,62),1)},{candidate:b,percent:round(clamp(50-lean,38,62),1)}];
}

function situationalVolatility(situation){
  const p=situation?.pressure||{};
  const shock=Math.max(0,Number(p.shock)||0),recomposition=Math.max(0,Number(p.recomposition)||0),macro=Math.abs(Number(p.macro_shift)||0);
  const lowQuality=Math.max(0,65-Number(situation?.quality?.score||0))/10;
  return clamp(3.5+shock*.28+recomposition*.18+macro*.12+lowQuality,3.5,15);
}

export function buildElectionOutcomeProjection(model,situation=null){
  const pairs=model?.first_round?.pair_scenarios||[];if(!pairs.length)return {schema:'providence-election-outcome-v1',status:'insufficient_pair_scenarios',candidates:[],pair_outcomes:[]};
  const first=firstRoundMap(model),h2h=headToHeadMap(model),candidateMass=new Map(),directMass=new Map(),inferredMass=new Map(),pairOutcomes=[];
  let directCoverage=0,totalMass=0;
  for(const pair of pairs){
    const names=Array.isArray(pair.candidates)&&pair.candidates.length===2?pair.candidates:(String(pair.title||'').split(':').at(-1)||'').split('/').map(x=>x.trim()).filter(Boolean).slice(0,2);
    if(names.length!==2)continue;
    const scenarioP=clamp(Number(pair.probability_percent)||0,0,100);if(!scenarioP)continue;totalMass+=scenarioP;
    const direct=h2h.get(matchupKey(names));let probs,method;
    if(direct?.model_win_probability?.length===2){probs=direct.model_win_probability.map(x=>({candidate:x.candidate,percent:Number(x.percent)}));method='direct_head_to_head';directCoverage+=scenarioP;}
    else {probs=conservativeSyntheticRunoff(names[0],names[1],first);method='synthetic_runoff_prior';}
    const normalized=probs.reduce((s,x)=>s+Number(x.percent||0),0)||100;
    const contributions=probs.map(x=>{const win=Number(x.percent||0)/normalized*100;const contribution=scenarioP*win/100;candidateMass.set(canon(x.candidate),(candidateMass.get(canon(x.candidate))||0)+contribution);const target=method==='direct_head_to_head'?directMass:inferredMass;target.set(canon(x.candidate),(target.get(canon(x.candidate))||0)+contribution);return {candidate:x.candidate,conditional_win_percent:round(win,1),overall_contribution_points:round(contribution,2)};});
    pairOutcomes.push({scenario_key:pair.scenario_key||null,title:pair.title||`Second tour : ${names.join(' / ')}`,configuration_probability_percent:round(scenarioP,1),method,conditional_outcome:contributions});
  }
  if(!totalMass)return {schema:'providence-election-outcome-v1',status:'insufficient_pair_scenarios',candidates:[],pair_outcomes:[]};
  const nameMap=new Map((model?.first_round?.candidates||[]).map(x=>[canon(x.candidate),x.candidate]));
  for(const po of pairOutcomes)for(const x of po.conditional_outcome)if(!nameMap.has(canon(x.candidate)))nameMap.set(canon(x.candidate),x.candidate);
  const volatility=situationalVolatility(situation),coverage=clamp(directCoverage/totalMass*100,0,100);
  const candidates=[...candidateMass.entries()].map(([key,mass])=>{
    const p=mass/totalMass*100;const direct=(directMass.get(key)||0)/totalMass*100,inferred=(inferredMass.get(key)||0)/totalMass*100;
    const intervalWidth=clamp(volatility+(100-coverage)*.055+(inferred>direct?2:0),4,20);
    return {candidate:nameMap.get(key)||key,victory_probability_percent:round(p,1),interval_percent:[round(Math.max(0,p-intervalWidth),1),round(Math.min(100,p+intervalWidth),1)],direct_head_to_head_contribution_points:round(direct,1),inferred_runoff_contribution_points:round(inferred,1)};
  }).sort((a,b)=>b.victory_probability_percent-a.victory_probability_percent);
  const total=candidates.reduce((s,x)=>s+x.victory_probability_percent,0);if(total>0&&Math.abs(total-100)>.2){for(const c of candidates)c.victory_probability_percent=round(c.victory_probability_percent/total*100,1);}
  const quality=clamp(Math.round(Number(model?.quality?.score||0)*.55+coverage*.35+Math.max(0,10-volatility)*1.0),0,92);
  return {
    schema:'providence-election-outcome-v1',status:'ok',generated_at:new Date().toISOString(),election:model?.election||'Élection',
    winner_projection:candidates[0]||null,candidates,pair_outcomes,
    coverage:{configuration_probability_mass:round(totalMass,1),direct_head_to_head_probability_mass:round(directCoverage,1),direct_head_to_head_coverage_percent:round(coverage,1),synthetic_runoff_coverage_percent:round(100-coverage,1)},
    situation:{inference_quality:Number(situation?.quality?.score||0),volatility_index:round(volatility,1),deductions_used:(situation?.deductions||[]).map(x=>x.id).slice(0,10)},
    quality:{score:quality,status:quality>=70?'substantial':quality>=50?'exploratory':'fragile'},
    methodology:{formula:'P(victoire candidat)=Σ P(configuration second tour) × P(victoire candidat | configuration)',direct_matchups:'Utilise le modèle de duel lorsqu’il existe.',missing_matchups:'Construit un prior de second tour très conservateur, ramené vers 50/50 et borné entre 38/62.',situational_inference:'Ajuste l’incertitude et la fragilité, pas arbitrairement le score d’un candidat.'},
    semantics:{this_is_a_model_projection:true,this_is_not_a_poll:true,this_is_not_certainty:true,synthetic_runoff_is_observed_data:false,situational_deductions_are_observed_data:false},
    warning:'La projection finale assemble plusieurs situations possibles. Les duels non mesurés sont volontairement traités avec un prior prudent ; les événements de campagne, reports de voix et candidatures définitives peuvent déplacer fortement le résultat.'
  };
}
