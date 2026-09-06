const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=3)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const clean=v=>String(v??'').replace(/\s+/g,' ').trim();

function fact(id,label,value,{family='derived_input',direction='neutral',strength=.5,source=null,meta={}}={}){
  return {id,label,value,family,direction,strength:round(clamp(strength,0,1),3),source,meta};
}

function macroFacts(evidence=[]){
  const row=evidence.find(x=>x?.family==='macro'&&x?.status==='ok');
  const out=[];
  for(const i of row?.metrics?.indicators||[]){
    const delta=Number(i?.delta);if(!Number.isFinite(delta))continue;
    const label=String(i?.label||'Indicateur macro');
    let direction='neutral',strength=Math.min(.9,.35+Math.abs(delta)*.09);
    if(label==='Inflation')direction=delta>.15?'stress':delta<-.15?'relief':'neutral';
    else if(label==='Chômage')direction=delta>.12?'stress':delta<-.12?'relief':'neutral';
    else if(label==='Croissance du PIB')direction=delta<-.2?'stress':delta>.2?'relief':'neutral';
    else if(label==='Dette publique')direction=delta>.5?'stress':delta<-.5?'relief':'neutral';
    out.push(fact(`macro:${i.key||label}`,`${label} : variation ${delta>0?'+':''}${round(delta,2)}`,{value:Number(i.value),year:i.year,delta},{family:'macro',direction,strength,source:row.label,meta:{indicator:i.key||null,previous:i.previous,previous_year:i.previous_year}}));
  }
  return out;
}

function mediaFacts(evidence=[]){
  const row=evidence.find(x=>x?.family==='media_attention'&&x?.status==='ok');if(!row)return[];
  const articles=Number(row?.metrics?.article_count||0),domains=Number(row?.metrics?.domain_count||0);
  if(!articles&&!domains)return[];
  const elevated=articles>=25||domains>=12;
  return [fact('media:breadth',`${articles} articles récents · ${domains} domaines médiatiques`,{articles,domains},{family:'media_attention',direction:elevated?'volatility':'neutral',strength:clamp(.25+domains/30+.15*Math.min(1,articles/50),.25,.9),source:row.label})];
}

function localForecastFacts(evidence=[]){
  const row=evidence.find(x=>x?.family==='forecast_engine');const matches=row?.metrics?.matches||[];if(!matches.length)return[];
  const probs=matches.map(x=>Number(x.probability_percent)).filter(Number.isFinite),confs=matches.map(x=>Number(x.confidence_score)).filter(Number.isFinite);
  const mean=probs.length?probs.reduce((a,b)=>a+b,0)/probs.length:null;
  const spread=probs.length>1?Math.max(...probs)-Math.min(...probs):0;
  const c=confs.length?confs.reduce((a,b)=>a+b,0)/confs.length:0;
  return [fact('local:forecast-cluster',`${matches.length} trajectoires Providence recoupent la question`,{matches:matches.length,mean_probability:round(mean,1),probability_spread:round(spread,1),mean_confidence:round(c,1)},{family:'forecast_engine',direction:spread>=25?'volatility':'convergence',strength:clamp(.35+matches.length*.05+c/300,.35,.92),source:row.label,meta:{scenario_keys:matches.map(x=>x.scenario_key).filter(Boolean).slice(0,10)}})];
}

function pollingFacts(evidence=[],electionModel=null){
  const out=[];
  const poll=evidence.find(x=>x?.family==='polling'&&x?.status==='ok');
  if(poll)out.push(fact('polling:coverage',`${Number(poll?.metrics?.poll_rows||0)} lignes de sondages structurées détectées`,{poll_rows:Number(poll?.metrics?.poll_rows||0)},{family:'polling',direction:'observed',strength:clamp(.35+Number(poll?.metrics?.poll_rows||0)/80,.35,.9),source:poll.label}));
  const rows=electionModel?.first_round?.candidates||[];
  if(rows.length>=3){
    const top=rows[0],second=rows[1],third=rows[2];
    out.push(fact('election:top-qualification',`${top.candidate} domine actuellement la probabilité de qualification`,{candidate:top.candidate,qualification_probability:Number(top.qualification_probability),poll_average:Number(top.poll_average)},{family:'election_model',direction:Number(top.qualification_probability)>=85?'lock':'lead',strength:clamp(Number(top.qualification_probability)/100,.4,.98),source:'Election Model'}));
    const gap=Math.abs(Number(second.qualification_probability)-Number(third.qualification_probability));
    out.push(fact('election:second-place-gap',`Écart de qualification entre ${second.candidate} et ${third.candidate} : ${round(gap,1)} points`,{second:second.candidate,third:third.candidate,gap},{family:'election_model',direction:gap<=20?'contest':'separation',strength:clamp(1-gap/70,.25,.9),source:'Election Model'}));
  }
  return out;
}

function independentFamilies(evidence=[]){return new Set(evidence.filter(x=>x?.status==='ok').map(x=>x.family).filter(Boolean));}

function deduceBase(facts,evidence,spec){
  const deductions=[];
  const stress=facts.filter(x=>x.family==='macro'&&x.direction==='stress');
  const relief=facts.filter(x=>x.family==='macro'&&x.direction==='relief');
  if(stress.length>=2){
    const confidence=clamp(.48+stress.reduce((s,x)=>s+x.strength,0)*.11,.5,.84);
    deductions.push({id:'deduction:macro-stress-cluster',label:'Pression socio-économique convergente',statement:`Plusieurs indicateurs macroéconomiques se dégradent simultanément. Cela augmente le risque de recomposition politique ou de rupture par rapport à une simple continuité.`,kind:'cross_signal_deduction',confidence:round(confidence,3),derived_from:stress.map(x=>x.id),mechanism:['dégradation simultanée de plusieurs indicateurs','pression sur les perceptions économiques','probabilité accrue de comportement électoral ou politique non linéaire'],branch_impacts:{continuity:-7,recomposition:4,macro_shift:8,shock:1},causal_proof:false});
  }
  if(relief.length>=2){
    const confidence=clamp(.45+relief.reduce((s,x)=>s+x.strength,0)*.1,.48,.8);
    deductions.push({id:'deduction:macro-relief-cluster',label:'Détente macroéconomique convergente',statement:'Plusieurs indicateurs évoluent dans un sens plus favorable. Cela renforce la continuité relative et réduit le poids d’un scénario de bascule purement économique.',kind:'cross_signal_deduction',confidence:round(confidence,3),derived_from:relief.map(x=>x.id),mechanism:['amélioration multi-indicateurs','réduction de la pression économique','moindre soutien au scénario de rupture macro'],branch_impacts:{continuity:7,recomposition:-2,macro_shift:-6,shock:0},causal_proof:false});
  }
  const media=facts.find(x=>x.id==='media:breadth');
  if(media?.direction==='volatility')deductions.push({id:'deduction:attention-volatility',label:'Environnement informationnel volatil',statement:'La diffusion du sujet sur de nombreux domaines médiatiques augmente la probabilité d’événements de campagne, de reconfiguration ou de chocs narratifs. L’attention médiatique n’est toutefois pas assimilée à une intention de vote.',kind:'contextual_deduction',confidence:round(clamp(media.strength*.72,.35,.7),3),derived_from:[media.id],mechanism:['forte dispersion médiatique','plus d’opportunités de rupture narrative','incertitude accrue'],branch_impacts:{continuity:-3,recomposition:2,macro_shift:0,shock:4},causal_proof:false});
  const lock=facts.find(x=>x.id==='election:top-qualification');
  if(lock?.direction==='lock')deductions.push({id:'deduction:first-slot-lock',label:'Première place de qualification relativement verrouillée',statement:`La probabilité de qualification du candidat actuellement en tête est suffisamment élevée pour que l’incertitude se concentre davantage sur l’adversaire du second tour que sur sa propre qualification.`,kind:'model_deduction',confidence:round(lock.strength*.9,3),derived_from:[lock.id],mechanism:['qualification très élevée','réduction de l’incertitude sur une place','transfert de l’incertitude vers la seconde place'],branch_impacts:{continuity:3,recomposition:2,macro_shift:0,shock:-1},causal_proof:false});
  const contest=facts.find(x=>x.id==='election:second-place-gap');
  if(contest?.direction==='contest')deductions.push({id:'deduction:second-place-contest',label:'Course ouverte pour la seconde qualification',statement:'L’écart de qualification entre les principaux poursuivants reste assez faible pour que des événements, alliances ou reports de voix puissent encore modifier la configuration finale.',kind:'model_deduction',confidence:round(contest.strength*.82,3),derived_from:[contest.id],mechanism:['écart de qualification limité','sensibilité aux événements de campagne','plusieurs configurations encore plausibles'],branch_impacts:{continuity:-2,recomposition:6,macro_shift:2,shock:2},causal_proof:false});
  const fam=independentFamilies(evidence);
  if(fam.size>=3)deductions.push({id:'deduction:independent-convergence',label:'Convergence de familles de données indépendantes',statement:`${fam.size} familles de données distinctes contribuent au dossier. Une conclusion commune devient plus crédible qu’un signal isolé, sans rendre les sources statistiquement indépendantes par défaut.`,kind:'evidence_structure_deduction',confidence:round(clamp(.45+fam.size*.06,.5,.82),3),derived_from:[...fam].map(x=>`family:${x}`),mechanism:['recoupement multi-familles','réduction de dépendance à une source unique'],branch_impacts:{continuity:1,recomposition:1,macro_shift:1,shock:0},causal_proof:false});
  return deductions;
}

function causalDeductions(snapshot={},evidence=[]){
  const graph=snapshot?.causal_world;const edges=graph?.edges||[],nodes=new Map((graph?.nodes||[]).map(n=>[n.id,n]));
  if(!edges.length)return[];
  const local=evidence.find(x=>x?.family==='forecast_engine');const keys=new Set((local?.metrics?.matches||[]).map(x=>x.scenario_key).filter(Boolean));
  if(!keys.size)return[];
  const rows=[];
  for(const edge of edges){
    if(edge?.type!=='structural_prior')continue;
    const from=nodes.get(edge.from),to=nodes.get(edge.to);if(!from?.scenario_key||!keys.has(from.scenario_key)||!to)continue;
    const learned=Boolean(edge?.learning?.active),strength=clamp(Number(edge.strength)||0,.05,.95);
    if(strength<.28)continue;
    rows.push({id:`deduction:causal:${from.scenario_key}:${to.scenario_key||to.id}`,label:`Propagation plausible vers « ${clean(to.label)} »`,statement:`La trajectoire « ${clean(from.label)} » possède un lien structurel ${learned?'ajusté par les résolutions historiques':'encore heuristique'} vers « ${clean(to.label)} ». Ce lien sert à explorer une conséquence possible, pas à prouver une causalité.`,kind:learned?'learned_structural_deduction':'structural_prior_deduction',confidence:round(strength*(learned?.95:.72),3),derived_from:[`forecast:${from.scenario_key}`,edge.from,edge.to],mechanism:[edge.rationale||'transition structurelle'],branch_impacts:{continuity:0,recomposition:1,macro_shift:to.domain==='economy_labor'||to.domain==='financial_stress'?3:1,shock:to.domain==='geopolitics_security'||to.domain==='natural_hazards'?3:0},learning:{active:learned,samples:Number(edge?.learning?.samples||0),strength},causal_proof:false,target:{scenario_key:to.scenario_key||null,title:to.label,domain:to.domain||null}});
  }
  return rows.sort((a,b)=>b.confidence-a.confidence).slice(0,5);
}

function pressureFrom(deductions=[]){
  const pressure={continuity:0,recomposition:0,macro_shift:0,shock:0};
  for(const d of deductions){const c=clamp(Number(d.confidence)||.5,.15,1);for(const k of Object.keys(pressure))pressure[k]+=Number(d?.branch_impacts?.[k]||0)*c;}
  return Object.fromEntries(Object.entries(pressure).map(([k,v])=>[k,round(v,2)]));
}

export function applyInferenceToBranchWeights(branches=[],situation=null){
  if(!Array.isArray(branches)||!branches.length)return branches;
  const p=situation?.pressure||{};const keyFor=(w,i)=>String(w.world_id||'').replace(/^dynamic_/,'')||['continuity','recomposition','macro_shift','shock'][i]||'continuity';
  const raw=branches.map((w,i)=>Math.max(3,Number(w.relative_world_weight_percent||0)+Number(p[keyFor(w,i)]||0)));
  const sum=raw.reduce((a,b)=>a+b,0)||1;let weights=raw.map(x=>round(x/sum*100,1));const drift=round(100-weights.reduce((a,b)=>a+b,0),1);weights[0]=round(weights[0]+drift,1);
  return branches.map((w,i)=>({...w,relative_world_weight_percent:weights[i],inference_adjustment_points:round(weights[i]-Number(w.relative_world_weight_percent||0),1),deduction_ids:(situation?.deductions||[]).filter(d=>Number(d?.branch_impacts?.[keyFor(w,i)]||0)!==0).map(d=>d.id).slice(0,6)}));
}

export function buildSituationalInference({spec={},evidence=[],snapshot={},electionModel=null}={}){
  const facts=[...macroFacts(evidence),...mediaFacts(evidence),...localForecastFacts(evidence),...pollingFacts(evidence,electionModel)];
  const deductions=[...deduceBase(facts,evidence,spec),...causalDeductions(snapshot,evidence)].sort((a,b)=>b.confidence-a.confidence);
  const pressure=pressureFrom(deductions);
  const learned=deductions.filter(x=>x?.learning?.active);
  const causalLearning=snapshot?.learning?.causal_learning||null;
  const quality=clamp(Math.round(25+Math.min(30,independentFamilies(evidence).size*7)+Math.min(25,deductions.length*4)+Math.min(20,learned.length*5)),0,95);
  return {
    schema:'providence-situational-inference-v1',generated_at:new Date().toISOString(),status:deductions.length?'active':'collecting',
    facts,deductions,pressure,quality:{score:quality,independent_evidence_families:independentFamilies(evidence).size,deduction_count:deductions.length,learned_deduction_count:learned.length},
    learning:{causal_learning_resolutions:Number(causalLearning?.resolved_forecasts||0),active_transitions:Number(causalLearning?.active_transitions||0),uses_learned_transitions:learned.length>0,mode:learned.length?'historical_association_adjusted':'heuristic_until_resolved'},
    semantics:{facts_are_observations:true,deductions_are_observations:false,deductions_are_causal_proof:false,learned_associations_are_intervention_effects:false,branch_weights_may_use_deductions:true,canonical_probabilities_changed:false},
    warning:'Les déductions combinent des faits et des relations structurelles. Elles servent à explorer des situations plausibles ; elles ne transforment pas une corrélation en causalité ni une intuition en probabilité publiée.'
  };
}
