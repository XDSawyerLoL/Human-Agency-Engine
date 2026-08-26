const STOPWORDS=new Set(['alors','avec','avant','avoir','cette','comme','comment','dans','des','donc','elle','elles','entre','est','faire','fait','faut','ici','ils','les','leur','mais','monde','nous','pour','plus','quelle','quelles','sera','serait','ses','son','sont','sur','une','vers','vont','vous','the','and','that','this','will','with','from','what','when','where']);

const DOMAIN_PATTERNS=[
  ['climate',['climat','climatique','température','temperature','réchauffement','rechauffement','sécheresse','secheresse','inondation','océan','ocean','météo','meteo']],
  ['economy',['économie','economie','inflation','emploi','chômage','chomage','croissance','récession','recession','pib','taux','marché','marche','bourse','prix']],
  ['geopolitics',['guerre','conflit','otan','nato','chine','russie','ukraine','iran','israël','israel','sanction','frontière','frontiere','géopolitique','geopolitique']],
  ['politics',['élection','election','président','president','gouvernement','parlement','politique','vote','parti','loi']],
  ['technology',['ia','intelligence artificielle','robot','technologie','semi-conducteur','semiconducteur','quantique','cyber','logiciel','ordinateur']],
  ['health',['santé','sante','maladie','épidémie','epidemie','pandémie','pandemie','vaccin','hôpital','hopital','médical','medical']],
  ['energy',['énergie','energie','électricité','electricite','pétrole','petrole','gaz','nucléaire','nucleaire','solaire','éolien','eolien']],
  ['science',['science','scientifique','recherche','espace','spatial','nasa','fusion','biotech','génétique','genetique']]
];

const HORIZON_LABELS={immediate:'0–30 jours',near:'1–6 mois',medium:'6–24 mois',long:'2–5 ans',strategic:'5 ans et +'};
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=3)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;

function cleanText(value){return String(value||'').replace(/\s+/g,' ').trim().slice(0,600);}
function normalize(value){return cleanText(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');}
function tokens(value){return [...new Set(normalize(value).split(/[^a-z0-9]+/).filter(x=>x.length>2&&!STOPWORDS.has(x)))];}

function inferDomain(question){
  const q=normalize(question);
  let best={domain:'general',score:0};
  for(const [domain,words] of DOMAIN_PATTERNS){
    const score=words.reduce((n,w)=>n+(q.includes(normalize(w))?1:0),0);
    if(score>best.score) best={domain,score};
  }
  return best.domain;
}

function explicitTargetDate(question,now){
  const yearMatch=normalize(question).match(/\b(20\d{2})\b/);
  if(yearMatch){
    const year=Number(yearMatch[1]);
    if(year>=now.getUTCFullYear()&&year<=now.getUTCFullYear()+30) return new Date(Date.UTC(year,11,31,23,59,59)).toISOString();
  }
  const years=normalize(question).match(/(?:dans|d'ici|within)\s+(\d{1,2})\s+(?:ans|annees|years?)/);
  if(years){const d=new Date(now);d.setUTCFullYear(d.getUTCFullYear()+Number(years[1]));return d.toISOString();}
  const months=normalize(question).match(/(?:dans|d'ici|within)\s+(\d{1,2})\s+(?:mois|months?)/);
  if(months){const d=new Date(now);d.setUTCMonth(d.getUTCMonth()+Number(months[1]));return d.toISOString();}
  return null;
}

function inferHorizon(question,targetDate,now){
  const q=normalize(question);
  if(/5\s*(?:ans|annees|years?)|10\s*(?:ans|annees|years?)|203[1-9]|204\d|205\d/.test(q)) return 'strategic';
  if(/3\s*(?:ans|annees|years?)|4\s*(?:ans|annees|years?)/.test(q)) return 'long';
  if(/2\s*(?:ans|annees|years?)|12\s*(?:mois|months?)|18\s*(?:mois|months?)/.test(q)) return 'medium';
  if(/semaine|week|mois|month|trimestre|quarter/.test(q)) return 'near';
  if(/demain|tomorrow|jours|days/.test(q)) return 'immediate';
  if(targetDate){
    const days=(Date.parse(targetDate)-now.getTime())/86400000;
    if(days<=30) return 'immediate'; if(days<=183) return 'near'; if(days<=730) return 'medium'; if(days<=1826) return 'long'; return 'strategic';
  }
  return 'medium';
}

function targetForHorizon(horizon,now){
  const d=new Date(now);
  if(horizon==='immediate') d.setUTCDate(d.getUTCDate()+30);
  else if(horizon==='near') d.setUTCMonth(d.getUTCMonth()+6);
  else if(horizon==='medium') d.setUTCFullYear(d.getUTCFullYear()+2);
  else if(horizon==='long') d.setUTCFullYear(d.getUTCFullYear()+5);
  else d.setUTCFullYear(d.getUTCFullYear()+7);
  return d.toISOString();
}

function similarity(question,forecast,domain){
  const a=tokens(question); if(!a.length) return 0;
  const text=[forecast?.title,forecast?.headline,forecast?.summary,forecast?.event_type,forecast?.domain,forecast?.region].filter(Boolean).join(' ');
  const b=new Set(tokens(text));
  const overlap=a.filter(x=>b.has(x)).length;
  const lexical=overlap/Math.max(3,a.length);
  const domainBoost=domain!=='general'&&String(forecast?.domain||'')===domain?.08:0;
  return clamp(lexical+domainBoost,0,1);
}

function matchForecasts(question,forecasts,domain){
  return (forecasts||[]).map(f=>({forecast:f,similarity:similarity(question,f,domain)}))
    .filter(x=>x.similarity>=.08)
    .sort((a,b)=>b.similarity-a.similarity)
    .slice(0,6)
    .map(x=>({
      scenario_key:x.forecast.scenario_key,
      title:x.forecast.title||x.forecast.headline,
      domain:x.forecast.domain,
      horizon_tier:x.forecast.horizon_tier,
      probability_percent:Number(x.forecast.probability?.percent??Math.round(Number(x.forecast.probability?.estimate||0)*100)),
      similarity:round(x.similarity),
      target_date:x.forecast.target_date||x.forecast.time_window?.end_at||null
    }));
}

function recompose(matches){
  if(matches.length<2) return {status:'insufficient_model_coverage',probability_percent:null,coverage_score:round(matches[0]?.similarity||0),matched_forecasts:matches.length};
  const strong=matches.filter(x=>x.similarity>=.12&&Number.isFinite(x.probability_percent));
  if(strong.length<2) return {status:'insufficient_model_coverage',probability_percent:null,coverage_score:round(matches.reduce((s,x)=>s+x.similarity,0)/Math.max(1,matches.length)),matched_forecasts:matches.length};
  const total=strong.reduce((s,x)=>s+Math.max(.05,x.similarity),0);
  const p=strong.reduce((s,x)=>s+(x.probability_percent/100)*Math.max(.05,x.similarity),0)/total;
  const variance=strong.reduce((s,x)=>s+Math.max(.05,x.similarity)*((x.probability_percent/100)-p)**2,0)/total;
  const spread=Math.sqrt(variance);
  const coverage=clamp(strong.reduce((s,x)=>s+x.similarity,0)/Math.max(1,strong.length)*1.6,0,1);
  return {
    status:coverage>=.25?'model_coverage':'weak_model_coverage',
    probability_percent:Math.round(p*100),
    interval_percent:[Math.max(2,Math.round((p-.12-spread*.6)*100)),Math.min(98,Math.round((p+.12+spread*.6)*100))],
    coverage_score:round(coverage),
    matched_forecasts:strong.length,
    method:'similarity-weighted recomposition of existing independently published forecasts'
  };
}

function makeSubForecasts(question,targetDate,domain,matches){
  const date=targetDate.slice(0,10);
  const central=`D’ici le ${date}, le scénario formulé par « ${question} » sera-t-il observable ?`;
  return [
    {
      key:'precursors',role:'leading_indicators',
      question:`Avant le ${date}, des indicateurs précurseurs indépendants compatibles avec « ${question} » apparaîtront-ils ?`,
      resolution_criterion:'OUI si au moins deux familles de sources indépendantes documentent des signaux précurseurs explicites avant l’échéance ; NON sinon.',
      probability_percent:null,status:'requires_signal_measurement'
    },
    {
      key:'central_event',role:'core_outcome',question:central,
      resolution_criterion:'OUI si une source officielle compétente, ou deux sources indépendantes de haute qualité, établissent que l’événement central tel que formulé s’est produit avant l’échéance ; NON si l’échéance passe sans réalisation.',
      ...recompose(matches)
    },
    {
      key:'persistence',role:'persistence',
      question:`Si le mouvement vers « ${question} » apparaît, restera-t-il mesurable pendant au moins 30 jours avant ou autour du ${date} ?`,
      resolution_criterion:'OUI si l’indicateur principal reste au-dessus de son seuil de déclenchement pendant au moins 30 jours cumulés ; NON si le signal se résorbe avant ce seuil.',
      probability_percent:null,status:'conditional_requires_metric'
    },
    {
      key:'second_order',role:'second_order_effect',
      question:`Une conséquence de second ordre attribuable au scénario « ${question} » sera-t-elle documentée avant le ${date} ?`,
      resolution_criterion:'OUI si une conséquence secondaire pré-définie et mesurable est observée avec une chaîne causale documentée ; NON si aucune conséquence définie n’est observée avant l’échéance.',
      probability_percent:null,status:'requires_causal_metric'
    }
  ].map(x=>({...x,domain,target_date:targetDate}));
}

export function compileForecastQuestion(rawQuestion,snapshot={},options={}){
  const question=cleanText(rawQuestion);
  if(question.length<8) throw new Error('question_too_short');
  const now=new Date(options.now||Date.now());
  if(Number.isNaN(now.getTime())) throw new Error('invalid_now');
  const domain=inferDomain(question);
  const explicit=explicitTargetDate(question,now);
  const horizon=inferHorizon(question,explicit,now);
  const targetDate=explicit||targetForHorizon(horizon,now);
  const matches=matchForecasts(question,snapshot?.forecasts||[],domain);
  const synthesis=recompose(matches);
  const subForecasts=makeSubForecasts(question,targetDate,domain,matches);
  const coverage=synthesis.coverage_score||0;

  return {
    schema:'evidence-forecast-compiler-v1',
    generated_at:now.toISOString(),
    input:{question},
    inferred:{domain,horizon_tier:horizon,horizon_label:HORIZON_LABELS[horizon],target_date:targetDate},
    resolution_contract:{
      kind:'binary_event',
      central_question:subForecasts.find(x=>x.key==='central_event')?.question,
      target_date:targetDate,
      falsifiable:true,
      ambiguity_warning:'La formulation libre est compilée automatiquement. Une métrique explicite améliore fortement la qualité de résolution.'
    },
    sub_forecasts:subForecasts,
    matched_forecasts:matches,
    synthesis,
    coverage:{
      score:round(coverage),
      status:coverage>=.25?'usable':coverage>=.12?'weak':'insufficient',
      numeric_probability_allowed:synthesis.probability_percent!==null
    },
    next_step:synthesis.probability_percent===null
      ?'Élargir la couverture du moteur ou préciser un indicateur, une zone et une échéance avant de publier un chiffre.'
      :'Conserver les sous-prévisions séparées dans le Track Record puis comparer la recomposition au résultat final.',
    guardrail:'Le compilateur refuse d’inventer une probabilité lorsqu’il ne trouve pas assez de prévisions publiées réellement pertinentes.'
  };
}
