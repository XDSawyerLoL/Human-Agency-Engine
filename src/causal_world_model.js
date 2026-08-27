const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=4)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const logit=p=>Math.log(clamp(p,.001,.999)/(1-clamp(p,.001,.999)));
const sigmoid=x=>1/(1+Math.exp(-x));

const STOP=new Set(['avec','dans','des','les','une','pour','sur','vers','plus','moins','hausse','baisse','risque','probable','probabilite','possibilite','autour','apres','avant','entre','dici','the','and','with','from','into','risk']);
const DOMAIN_LABELS={
  natural_hazards:'Risques naturels',weather_climate:'Climat & météo',cyber_technology:'Technologie & cyber',public_health:'Santé publique',
  financial_stress:'Stress financier',energy:'Énergie',economy_labor:'Économie & emploi',supply_fuel:'Approvisionnement',
  social_collective_behavior:'Comportements collectifs',geopolitics_security:'Géopolitique & sécurité',regulation_policy:'Régulation & politiques',transport_mobility:'Transport & mobilité'
};

// Priors structurels généraux. Ils servent à explorer des mécanismes plausibles, jamais à prétendre démontrer une causalité.
// Les chocs naturels ne sautent pas directement vers l'économie : l'effet doit passer par un mécanisme intermédiaire observable (transport, approvisionnement, santé ou politique).
const DOMAIN_TRANSITIONS={
  natural_hazards:[['transport_mobility',.62],['supply_fuel',.60],['regulation_policy',.44],['public_health',.34]],
  weather_climate:[['transport_mobility',.60],['energy',.54],['supply_fuel',.48],['economy_labor',.43],['regulation_policy',.40]],
  geopolitics_security:[['supply_fuel',.68],['energy',.61],['financial_stress',.54],['economy_labor',.50],['regulation_policy',.47]],
  supply_fuel:[['economy_labor',.70],['transport_mobility',.46],['financial_stress',.37],['regulation_policy',.34]],
  energy:[['economy_labor',.68],['regulation_policy',.53],['supply_fuel',.43]],
  financial_stress:[['economy_labor',.72],['regulation_policy',.54],['social_collective_behavior',.43]],
  economy_labor:[['social_collective_behavior',.59],['regulation_policy',.45],['financial_stress',.38]],
  public_health:[['social_collective_behavior',.56],['regulation_policy',.53],['economy_labor',.47],['transport_mobility',.34]],
  cyber_technology:[['regulation_policy',.54],['economy_labor',.45],['supply_fuel',.34],['transport_mobility',.30]],
  social_collective_behavior:[['regulation_policy',.65],['economy_labor',.42],['transport_mobility',.36]],
  transport_mobility:[['supply_fuel',.66],['economy_labor',.55]],
  regulation_policy:[['economy_labor',.43],['energy',.37],['cyber_technology',.36]]
};

function normalize(value){return String(value||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();}
function slug(value){return normalize(value).split(' ').filter(Boolean).slice(0,8).join('-').slice(0,72)||'node';}
function hash(value){
  let h=2166136261;
  for(const ch of String(value||'')){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}
  return (h>>>0).toString(36);
}
function conceptId(label){return `concept:${slug(label)}:${hash(normalize(label))}`;}
function tokens(value){return new Set(normalize(value).split(' ').filter(x=>x.length>2&&!STOP.has(x)));}
function similarity(a,b){
  const A=tokens(a),B=tokens(b); if(!A.size||!B.size) return 0;
  let common=0; for(const x of A) if(B.has(x)) common++;
  return common/Math.max(2,Math.min(A.size,B.size));
}
function probability(f){return clamp(Number(f?.probability?.estimate ?? Number(f?.probability?.percent||0)/100),.02,.98);}
function confidence(f){return clamp(Number(f?.confidence_breakdown?.score||f?.confidence||50)/100,.2,.98);}
function horizonOrder(f){return Number.isFinite(Number(f?.horizon_order))?Number(f.horizon_order):({immediate:0,near:1,medium:2,long:3,strategic:4}[f?.horizon_tier]??2);}
function compactRegion(value){return normalize(value||'monde');}

function addNode(nodes,node){
  const current=nodes.get(node.id);
  if(!current) nodes.set(node.id,node);
  else if(node.type==='concept') current.references=(current.references||0)+1;
  return nodes.get(node.id);
}
function edgeKey(edge){return `${edge.from}|${edge.to}|${edge.type}`;}
function addEdge(edges,edge){
  if(!edge.from||!edge.to||edge.from===edge.to) return;
  const key=edgeKey(edge); const old=edges.get(key);
  if(!old) edges.set(key,edge);
  else {
    old.strength=round(Math.max(Number(old.strength)||0,Number(edge.strength)||0),3);
    old.support_count=(old.support_count||1)+1;
    old.scenario_keys=[...new Set([...(old.scenario_keys||[]),...(edge.scenario_keys||[])])].slice(0,8);
  }
}

function transitionStrength(fromDomain,toDomain){
  const row=(DOMAIN_TRANSITIONS[fromDomain]||[]).find(([d])=>d===toDomain);
  return row?row[1]:null;
}

function pairContext(a,b){
  const sameOrigin=Boolean(a.origin_group&&b.origin_group&&a.origin_group===b.origin_group);
  const ra=compactRegion(a.region),rb=compactRegion(b.region);
  const sameRegion=Boolean(ra&&rb&&ra!=='monde'&&rb!=='monde'&&ra===rb);
  const lexical=similarity([...(a.causal_chain||[]).slice(-2),a.title,a.summary].join(' '),[...(b.causal_chain||[]).slice(0,2),b.what_we_know,b.title].join(' '));
  return {sameOrigin,sameRegion,lexical,score:(sameOrigin ? .55 : 0)+(sameRegion ? .25 : 0)+lexical*.35};
}

function graphMetrics(nodes,edges){
  const nodeList=[...nodes.values()],edgeList=[...edges.values()];
  const outgoing=new Map();
  for(const e of edgeList){const arr=outgoing.get(e.from)||[];arr.push(e);outgoing.set(e.from,arr);}
  const reach=(start,maxDepth=3)=>{
    const seen=new Set([start]); let frontier=[start];
    for(let depth=0;depth<maxDepth;depth++){
      const next=[];
      for(const id of frontier) for(const e of outgoing.get(id)||[]) if(!seen.has(e.to)){seen.add(e.to);next.push(e.to);}
      frontier=next; if(!frontier.length) break;
    }
    return seen.size-1;
  };
  const leverage=nodeList.filter(n=>n.type!=='source').map(n=>{
    const outs=outgoing.get(n.id)||[];
    const strength=outs.reduce((s,e)=>s+Number(e.strength||0),0);
    const downstream=reach(n.id,3);
    return {node_id:n.id,label:n.label,type:n.type,domain:n.domain||null,leverage_score:round(strength+downstream*.07,3),downstream_nodes:downstream,outgoing_edges:outs.length};
  }).sort((a,b)=>b.leverage_score-a.leverage_score).slice(0,16);
  const types=edgeList.reduce((a,e)=>{a[e.type]=(a[e.type]||0)+1;return a;},{});
  return {
    nodes:nodeList.length,edges:edgeList.length,
    forecast_nodes:nodeList.filter(n=>n.type==='forecast').length,
    concept_nodes:nodeList.filter(n=>n.type==='concept').length,
    source_nodes:nodeList.filter(n=>n.type==='source').length,
    edge_types:types,
    evidence_backed_edges:(types.evidence_support||0),
    hypothesis_edges:(types.mechanism_hypothesis||0)+(types.structural_prior||0),
    top_leverage:leverage
  };
}

export function buildCausalWorldModel(forecasts=[]){
  const nodes=new Map(),edges=new Map();
  const compactForecasts=(forecasts||[]).filter(f=>f?.scenario_key).slice(0,100);

  for(const f of compactForecasts){
    const fid=`forecast:${f.scenario_key}`;
    addNode(nodes,{id:fid,type:'forecast',scenario_key:f.scenario_key,label:String(f.title||f.headline||f.scenario_key).slice(0,180),domain:f.domain||'unknown',domain_label:DOMAIN_LABELS[f.domain]||f.domain||'Autre',region:f.region||'Monde',horizon_tier:f.horizon_tier||null,horizon_order:horizonOrder(f),target_date:f.target_date||f.time_window?.end_at||null,probability:round(probability(f),4),probability_percent:Math.round(probability(f)*100),confidence:round(confidence(f),3)});
    const chain=(Array.isArray(f.causal_chain)?f.causal_chain:[]).map(x=>String(x||'').trim()).filter(Boolean).slice(0,8);
    const conceptIds=[];
    for(const label of chain){
      const cid=conceptId(label);conceptIds.push(cid);
      addNode(nodes,{id:cid,type:'concept',label:label.slice(0,160),domain:f.domain||null,references:1});
    }
    for(let i=0;i<conceptIds.length-1;i++) addEdge(edges,{from:conceptIds[i],to:conceptIds[i+1],type:'mechanism_hypothesis',polarity:1,strength:round(.42+confidence(f)*.28,3),status:'model_hypothesis',scenario_keys:[f.scenario_key],rationale:'Étape explicitement déclarée dans la chaîne causale du scénario.'});
    if(conceptIds.length) addEdge(edges,{from:conceptIds.at(-1),to:fid,type:'outcome_definition',polarity:1,strength:.92,status:'definition',scenario_keys:[f.scenario_key],rationale:'Le dernier mécanisme définit l’issue observable de la prévision.'});

    const first=conceptIds[0];
    if(first){
      for(const e of (f.evidence||[]).slice(0,4)){
        const sourceKey=String(e.source_key||e.source_label||'source');
        const sid=`source:${slug(sourceKey)}`;
        addNode(nodes,{id:sid,type:'source',label:e.source_label||sourceKey,source_key:e.source_key||sourceKey,source_family:e.source_family||null});
        addEdge(edges,{from:sid,to:first,type:'evidence_support',polarity:1,strength:round(clamp(Number(e.source_trust)||.65,.25,.99),3),status:'observed_support',scenario_keys:[f.scenario_key],rationale:'Source utilisée comme précurseur ou preuve d’entrée par le moteur.'});
      }
    }
  }

  // Lien inter-scénarios uniquement s’il existe un prior de domaine et un contexte partagé suffisant.
  for(let i=0;i<compactForecasts.length;i++) for(let j=0;j<compactForecasts.length;j++){
    if(i===j) continue;
    const a=compactForecasts[i],b=compactForecasts[j];
    if(horizonOrder(a)>horizonOrder(b)) continue;
    const prior=transitionStrength(a.domain,b.domain); if(prior===null) continue;
    const ctx=pairContext(a,b); if(ctx.score<.45) continue;
    const temporalPenalty=horizonOrder(a)===horizonOrder(b) ? .82 : 1;
    const strength=clamp(prior*(.68+Math.min(.32,ctx.score*.25))*temporalPenalty,.12,.72);
    addEdge(edges,{from:`forecast:${a.scenario_key}`,to:`forecast:${b.scenario_key}`,type:'structural_prior',polarity:1,strength:round(strength,3),status:'heuristic_hypothesis',scenario_keys:[a.scenario_key,b.scenario_key],rationale:`Prior structurel ${DOMAIN_LABELS[a.domain]||a.domain} → ${DOMAIN_LABELS[b.domain]||b.domain}; contexte partagé=${round(ctx.score,2)}.`,context:{same_origin:ctx.sameOrigin,same_region:ctx.sameRegion,lexical_similarity:round(ctx.lexical,3)}});
  }

  const nodeList=[...nodes.values()];
  const edgeList=[...edges.values()];
  const metrics=graphMetrics(nodes,edges);
  return {
    schema:'evidence-causal-world-v1',
    generated_at:new Date().toISOString(),
    status:'experimental_causal_hypothesis_graph',
    nodes:nodeList,
    edges:edgeList,
    metrics,
    methodology:{
      evidence_support:'Relie une source réellement utilisée au premier mécanisme du scénario.',
      mechanism_hypothesis:'Relie les étapes de causal_chain explicitement produites par le moteur.',
      outcome_definition:'Relie le mécanisme final à l’issue prévue.',
      structural_prior:'Lien inter-scénarios heuristique, activé seulement avec un prior de domaine et un contexte partagé suffisant.'
    },
    contract:{causal_proof:false,structural_priors_are_facts:false,simulation_replaces_forecast:false,graph_is_a_decision_aid:true},
    warning:'Le graphe cartographie des mécanismes plausibles et des dépendances hypothétiques. Il ne prouve pas la causalité et ne doit pas être lu comme une simulation exhaustive du monde.'
  };
}

export function attachCausalContext(forecasts=[],graph){
  const edges=graph?.edges||[]; const leverage=new Map((graph?.metrics?.top_leverage||[]).map(x=>[x.node_id,x]));
  const labelById=new Map((graph?.nodes||[]).map(n=>[n.id,n.label]));
  for(const f of forecasts){
    const id=`forecast:${f.scenario_key}`;
    const incoming=edges.filter(e=>e.to===id&&e.from.startsWith('forecast:')).sort((a,b)=>b.strength-a.strength).slice(0,5);
    const outgoing=edges.filter(e=>e.from===id&&e.to.startsWith('forecast:')).sort((a,b)=>b.strength-a.strength).slice(0,5);
    f.causal_context={
      graph_node_id:id,
      leverage_score:leverage.get(id)?.leverage_score||0,
      upstream_scenarios:incoming.map(e=>({scenario_key:e.from.replace('forecast:',''),label:labelById.get(e.from)||e.from,strength:e.strength,status:e.status})),
      downstream_scenarios:outgoing.map(e=>({scenario_key:e.to.replace('forecast:',''),label:labelById.get(e.to)||e.to,strength:e.strength,status:e.status})),
      causal_proof:false
    };
  }
  return forecasts;
}

function resolveTargets(graph,intervention){
  const nodes=graph?.nodes||[];
  const explicit=String(intervention?.node_id||intervention?.target||'').trim();
  const domain=String(intervention?.domain||'').trim();
  if(explicit){
    const direct=nodes.find(n=>n.id===explicit||n.scenario_key===explicit);
    if(direct) return [direct];
    if(explicit.startsWith('domain:')) return nodes.filter(n=>n.type==='forecast'&&n.domain===explicit.slice(7));
    const q=normalize(explicit);
    const matched=nodes.filter(n=>normalize(n.label).includes(q)||q.includes(normalize(n.label))).slice(0,8);
    if(matched.length) return matched;
  }
  if(domain) return nodes.filter(n=>n.type==='forecast'&&n.domain===domain).slice(0,20);
  return [];
}

function edgeTransmission(edge){
  const typeFactor={evidence_support:.45,mechanism_hypothesis:.72,outcome_definition:.92,structural_prior:.58}[edge.type]??.5;
  return clamp(Number(edge.strength||0)*typeFactor,.03,.85)*(Number(edge.polarity||1)>=0?1:-1);
}

export function simulateCausalScenario(graph,forecasts=[],rawInterventions=[],options={}){
  if(!graph?.nodes?.length) throw new Error('causal_graph_unavailable');
  const interventions=(Array.isArray(rawInterventions)?rawInterventions:[]).slice(0,8);
  if(!interventions.length) throw new Error('intervention_required');
  const maxHops=clamp(Number(options.max_hops||4),1,5);
  const outgoing=new Map(); for(const e of graph.edges||[]){const arr=outgoing.get(e.from)||[];arr.push(e);outgoing.set(e.from,arr);}
  const nodeById=new Map(graph.nodes.map(n=>[n.id,n]));
  const influence=new Map(); const pathsByForecast=new Map(); const applied=[];

  for(const intervention of interventions){
    const direction=String(intervention.direction||'up').toLowerCase()==='down'?-1:1;
    const strength=clamp(Number(intervention.strength||1),.2,3);
    const starts=resolveTargets(graph,intervention);
    if(!starts.length){applied.push({target:intervention.target||intervention.node_id||intervention.domain,status:'unmatched'});continue;}
    applied.push({target:intervention.target||intervention.node_id||intervention.domain,direction:direction>0?'up':'down',strength,matched_nodes:starts.map(n=>({id:n.id,label:n.label,type:n.type})).slice(0,8),status:'applied'});

    for(const start of starts){
      const queue=[{id:start.id,impulse:direction*strength,depth:0,path:[start.id]}];
      const best=new Map([[start.id,Math.abs(direction*strength)]]);
      while(queue.length){
        const cur=queue.shift(); const node=nodeById.get(cur.id);
        if(node?.type==='forecast'){
          influence.set(cur.id,clamp((influence.get(cur.id)||0)+cur.impulse,-4,4));
          const arr=pathsByForecast.get(cur.id)||[];
          arr.push({impact:round(cur.impulse,4),hops:cur.depth,path:cur.path.map(id=>({id,label:nodeById.get(id)?.label||id,type:nodeById.get(id)?.type||'unknown'}))});
          pathsByForecast.set(cur.id,arr.sort((a,b)=>Math.abs(b.impact)-Math.abs(a.impact)).slice(0,4));
        }
        if(cur.depth>=maxHops) continue;
        for(const edge of outgoing.get(cur.id)||[]){
          if(cur.path.includes(edge.to)) continue;
          const nextImpulse=cur.impulse*edgeTransmission(edge)*(.82**cur.depth);
          if(Math.abs(nextImpulse)<.025) continue;
          if(Math.abs(nextImpulse)<=(best.get(edge.to)||0)*.72) continue;
          best.set(edge.to,Math.max(best.get(edge.to)||0,Math.abs(nextImpulse)));
          queue.push({id:edge.to,impulse:nextImpulse,depth:cur.depth+1,path:[...cur.path,edge.to]});
        }
      }
    }
  }

  const affected=[];
  for(const f of forecasts||[]){
    const id=`forecast:${f.scenario_key}`; const raw=influence.get(id)||0; if(Math.abs(raw)<.02) continue;
    const base=probability(f);
    const simulated=clamp(sigmoid(logit(base)+raw*.42),.01,.99);
    const delta=Math.round((simulated-base)*100);
    affected.push({
      scenario_key:f.scenario_key,title:f.title||f.headline,domain:f.domain,horizon_tier:f.horizon_tier,target_date:f.target_date||f.time_window?.end_at||null,
      base_probability_percent:Math.round(base*100),simulated_probability_percent:Math.round(simulated*100),delta_points:delta,
      influence_score:round(raw,4),paths:pathsByForecast.get(id)||[]
    });
  }
  affected.sort((a,b)=>Math.abs(b.delta_points)-Math.abs(a.delta_points)||Math.abs(b.influence_score)-Math.abs(a.influence_score));

  return {
    schema:'evidence-scenario-lab-v1',
    generated_at:new Date().toISOString(),
    mode:'causal_sensitivity_propagation',
    interventions:applied,
    max_hops:maxHops,
    affected_forecasts:affected.slice(0,30),
    summary:{affected:affected.length,rising:affected.filter(x=>x.delta_points>0).length,falling:affected.filter(x=>x.delta_points<0).length,max_absolute_delta_points:affected.reduce((m,x)=>Math.max(m,Math.abs(x.delta_points)),0),second_order_effects:affected.filter(x=>(x.paths||[]).some(p=>p.hops>=2)).length},
    guardrails:{is_causal_proof:false,is_exhaustive_world_simulation:false,replaces_public_probability:false,structural_priors_are_hypotheses:true},
    note:'Le Scenario Lab mesure une sensibilité conditionnelle dans le graphe ÉVIDENCE. Les probabilités simulées sont des déplacements contrefactuels, pas de nouvelles prévisions publiées.'
  };
}
