const clean=v=>String(v??'').replace(/\s+/g,' ').trim();
const norm=v=>clean(v).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=2)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const canon=name=>norm(name).replace(/\b(mme|m|monsieur|madame)\b/g,'').trim();

const GROUPS={
  polling:'polling',forecast_engine:'model_output',macro:'macro_conditions',macro_independent_eu:'macro_conditions',media_attention:'media_attention',institutional_context:'institutional_context',lobbying_transparency:'institutional_influence',independent_remote:'other'
};

function dedupeEvidence(evidence=[]){
  const seen=new Set(),unique=[],duplicates=[];
  for(const item of evidence){
    if(!item)continue;
    const group=item.correlation_group||GROUPS[item.family]||item.family||'other';
    const owner=item.independence?.source_owner||item.label||item.id||'unknown';
    const key=`${group}|${norm(owner)}|${norm(item.id||item.label||'')}`;
    if(seen.has(key)){duplicates.push({...item,correlation_group:group});continue;}
    seen.add(key);unique.push({...item,correlation_group:group});
  }
  const ok=unique.filter(x=>x.status==='ok');
  const ownerCount=new Set(ok.map(x=>x.independence?.source_owner||x.label||x.id)).size;
  const groupCount=new Set(ok.map(x=>x.correlation_group)).size;
  const score=Math.round(clamp((ownerCount*.65+groupCount*.35)/Math.max(1,ok.length),0,1)*100);
  return {unique,duplicates,owner_count:ownerCount,correlation_group_count:groupCount,independence_score:score};
}

function matchupKey(names=[]){return names.map(canon).filter(Boolean).sort().join('|');}
function h2hMap(secondRound=[]){
  const map=new Map();
  for(const row of secondRound||[]){
    const key=matchupKey(row?.matchup||[]);if(!key)continue;
    map.set(key,row);
  }
  return map;
}

function finalOutcome(model){
  const pairs=model?.first_round?.pair_scenarios||[];
  const h2h=h2hMap(model?.second_round||[]);
  const wins=new Map(),paths=[],unresolved=[];
  let coveredMass=0,totalMass=0;
  for(const pair of pairs){
    const pairP=clamp(Number(pair?.probability_percent),0,100)/100;if(!pairP)continue;
    totalMass+=pairP;
    const key=matchupKey(pair.candidates||[]),duel=h2h.get(key);
    if(!duel||!Array.isArray(duel.model_win_probability)||duel.model_win_probability.length!==2){unresolved.push({title:pair.title,probability_percent:round(pairP*100,1),reason:'aucun sondage de duel suffisamment structuré'});continue;}
    const probs=duel.model_win_probability.map(x=>({candidate:x.candidate,percent:clamp(Number(x.percent),0,100)}));
    const sum=probs.reduce((s,x)=>s+x.percent,0)||100;
    coveredMass+=pairP;
    for(const p of probs){
      const conditional=p.percent/sum;
      const contribution=pairP*conditional;
      const keyCandidate=canon(p.candidate);const row=wins.get(keyCandidate)||{candidate:p.candidate,probability:0,paths:[]};
      row.probability+=contribution;row.paths.push({matchup:pair.title,pair_probability_percent:round(pairP*100,1),conditional_win_probability_percent:round(conditional*100,1),contribution_percent:round(contribution*100,1),polls:duel.polls||0});wins.set(keyCandidate,row);
    }
    paths.push({matchup:pair.title,pair_probability_percent:round(pairP*100,1),conditional_win_probability:probs,polls:duel.polls||0});
  }
  const candidates=[...wins.values()].map(x=>({...x,win_probability_percent:round(x.probability*100,1)})).sort((a,b)=>b.win_probability_percent-a.win_probability_percent).map(({probability,...x})=>x);
  const coveragePercent=round(clamp(coveredMass/Math.max(.0001,totalMass),0,1)*100,1);
  const unresolvedPercent=round(clamp((totalMass-coveredMass),0,1)*100,1);
  const publish=coveredMass>=.55&&candidates.length>=2;
  return {
    status:publish?'publishable':'partial',coverage_percent:coveragePercent,unresolved_probability_mass_percent:unresolvedPercent,
    winner:candidates[0]||null,candidates,paths,unresolved,
    semantics:{win_probability_is_unconditional_across_covered_second_round_paths:true,unresolved_mass_is_not_redistributed:true,head_to_head_required_for_candidate_shift:true}
  };
}

function entropy(probs=[]){
  const xs=probs.map(Number).filter(x=>x>0);const s=xs.reduce((a,b)=>a+b,0)||1;
  return -xs.reduce((a,x)=>{const p=x/s;return a+p*Math.log2(p);},0);
}

function macroFeatures(evidence){
  const rows=[];
  for(const e of evidence.filter(x=>x.status==='ok'&&x.correlation_group==='macro_conditions')){
    for(const i of e.metrics?.indicators||[])rows.push({source:e.label,label:i.label||i.key,value:Number(i.value),delta:Number(i.delta),period:i.period||i.year||null});
  }
  const stressRows=rows.filter(x=>/inflation|ch[ôo]mage|dette/i.test(x.label));
  const rising=stressRows.filter(x=>Number.isFinite(x.delta)&&x.delta>0).length;
  const falling=stressRows.filter(x=>Number.isFinite(x.delta)&&x.delta<0).length;
  const independentSources=new Set(rows.map(x=>x.source)).size;
  return {observations:rows.length,independent_sources:independentSources,rising_stress_count:rising,falling_stress_count:falling,stress_balance:rising-falling,rows};
}

function mediaFeature(evidence){
  const e=evidence.find(x=>x.status==='ok'&&x.correlation_group==='media_attention');
  if(!e)return {available:false,domain_count:0,article_count:0,volatility_index:0};
  const domains=Number(e.metrics?.domain_count)||0,articles=Number(e.metrics?.article_count)||0;
  return {available:true,domain_count:domains,article_count:articles,volatility_index:round(clamp(domains/25*.6+articles/50*.4,0,1),3)};
}

function deductions(model,evidenceReport,outcome){
  const pairs=model?.first_round?.pair_scenarios||[];
  const candidates=model?.first_round?.candidates||[];
  const topPair=Number(pairs[0]?.probability_percent)||0;
  const topQual=Number(candidates[0]?.qualification_probability)||0;
  const secondQual=Number(candidates[1]?.qualification_probability)||0;
  const thirdQual=Number(candidates[2]?.qualification_probability)||0;
  const pairEntropy=round(entropy(pairs.map(x=>Number(x.probability_percent)||0)),3);
  const macro=macroFeatures(evidenceReport.unique),media=mediaFeature(evidenceReport.unique);
  const rows=[];
  if(topQual>=90)rows.push({key:'dominant_qualification',strength:'forte',statement:`${candidates[0]?.candidate||'Le candidat en tête'} apparaît presque verrouillé pour la qualification au second tour dans les simulations actuelles.`,derived_from:['first_round_qualification_distribution']});
  if(Math.abs(secondQual-thirdQual)<=12)rows.push({key:'second_slot_competition',strength:'forte',statement:'La deuxième place reste structurellement disputée : plusieurs lignes temporelles peuvent encore mener à des seconds tours différents.',derived_from:['qualification_gap','pair_distribution']});
  if(topPair<60)rows.push({key:'fragmented_second_round',strength:'moyenne',statement:'Aucune configuration de second tour n’écrase complètement les autres ; le système doit conserver plusieurs branches actives.',derived_from:['pair_concentration','pair_entropy']});
  else rows.push({key:'concentrated_second_round',strength:'moyenne',statement:'Une configuration de second tour domine nettement, mais les branches alternatives restent conservées tant que leur masse n’est pas négligeable.',derived_from:['pair_concentration','pair_entropy']});
  if(macro.independent_sources>=2)rows.push({key:'macro_cross_source',strength:'moyenne',statement:`Le contexte macroéconomique est recoupé par ${macro.independent_sources} sources statistiques indépendantes. Il sert de variable de régime, pas de bonus automatique pour un candidat.`,derived_from:['macro_cross_source_convergence']});
  if(media.available&&media.volatility_index>=.45)rows.push({key:'attention_volatility',strength:'faible',statement:'L’attention médiatique est suffisamment dispersée pour augmenter le risque de rupture de trajectoire ; elle n’est pas assimilée à une intention de vote.',derived_from:['media_dispersion']});
  if(evidenceReport.unique.some(x=>x.status==='ok'&&x.family==='lobbying_transparency'))rows.push({key:'lobbying_context',strength:'contextuelle',statement:'Les données HATVP peuvent alimenter un graphe d’influence documenté, mais elles restent hors du calcul électoral tant qu’aucun effet historique n’est calibré.',derived_from:['hatvp_transparency']});
  if(outcome.status==='publishable')rows.unshift({key:'final_result',strength:'forte',statement:`Le calcul final combine la probabilité de chaque configuration de second tour avec la probabilité conditionnelle de victoire dans les duels effectivement documentés. Couverture actuelle : ${outcome.coverage_percent}%.`,derived_from:['pair_probability','head_to_head_probability']});
  return {rows,features:{top_qualification_probability:round(topQual,1),second_qualification_probability:round(secondQual,1),third_qualification_probability:round(thirdQual,1),second_third_gap_points:round(Math.abs(secondQual-thirdQual),1),top_pair_probability:round(topPair,1),pair_entropy_bits:pairEntropy,head_to_head_coverage_percent:outcome.coverage_percent,macro_stress_balance:macro.stress_balance,macro_independent_sources:macro.independent_sources,media_volatility_index:media.volatility_index,source_independence_score:evidenceReport.independence_score}};
}

export function buildElectionDeduction({electionModel,dynamicForecast}={}){
  if(!electionModel)return null;
  const evidence=dynamicForecast?.research?.evidence||[];
  const evidenceReport=dedupeEvidence(evidence);
  const outcome=finalOutcome(electionModel);
  const inference=deductions(electionModel,evidenceReport,outcome);
  return {
    schema:'providence-election-deduction-v1',generated_at:new Date().toISOString(),status:'ok',
    final_outcome:outcome,deductions:inference.rows,learning_features:inference.features,
    evidence_independence:{score:evidenceReport.independence_score,independent_source_owners:evidenceReport.owner_count,correlation_groups:evidenceReport.correlation_group_count,duplicates_suppressed:evidenceReport.duplicates.length,groups:[...new Set(evidenceReport.unique.filter(x=>x.status==='ok').map(x=>x.correlation_group))]},
    learning:{ready:true,principle:'Les variables dérivées sont enregistrées comme features stables afin de pouvoir mesurer, après résolution, lesquelles améliorent réellement les prévisions.',candidate_probability_inputs:['probabilité de configuration du second tour','sondages de duel structurés'],context_only_inputs:['macroéconomie','attention médiatique','lobbying/transparence','métadonnées institutionnelles'],no_double_counting:true},
    guardrails:{correlated_sources_grouped:true,unresolved_probability_mass_not_redistributed:true,context_never_becomes_candidate_bonus_without_calibration:true}
  };
}
