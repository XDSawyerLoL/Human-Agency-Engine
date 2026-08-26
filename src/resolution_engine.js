const STOP = new Set(`a à au aux avec ce ces dans de des du elle en et eux il je la le les leur lui mais mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur un une vos votre vous the of and or will what when who how before after by from into over under be is are was were to in on at as an any its this that than more less global world monde`.split(/\s+/));
const normalize = v => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
const tokens = v => [...new Set(normalize(v).split(/\s+/).filter(x=>x.length>=4&&!STOP.has(x)))];
const clamp = (v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));

export function classifyResolutionKind(forecast = {}) {
  const title = String(forecast.title || forecast.headline || '').trim();
  const lower = title.toLowerCase();
  if (/^(what|when|who|how many|how much|quel|quelle|quand|qui)\b/.test(lower)) return 'open_question';
  if (/\b(score|prix moyen|valeur exacte|total damage|highest score)\b/.test(lower)) return 'numeric';
  return 'binary_event';
}

export function resolutionContract(forecast = {}) {
  const kind = forecast?.resolution_contract?.kind || classifyResolutionKind(forecast);
  return {
    kind,
    machine_rule: forecast?.resolution_contract?.machine_rule || null,
    criteria: forecast?.resolution_conditions || forecast?.falsification || 'Résoudre selon la formulation publiée et l’échéance déclarée.',
    target_at: forecast?.target_date || forecast?.time_window?.end_at || null,
    eligible_for_binary_scoring: kind === 'binary_event'
  };
}

function signalText(s){return normalize(`${s?.title||''} ${s?.event_type||''} ${s?.geography||''} ${s?.source_label||''} ${JSON.stringify(s?.facts||{})}`)}

function evidenceMatches(row, signals = []) {
  const meta = row?.meta || {};
  const forecast = meta.forecast || meta;
  const titleTokens = tokens(`${row?.title||''} ${forecast?.summary||''} ${forecast?.region||''}`);
  const region = normalize(forecast?.region || row?.region || '');
  const matches = [];
  for (const s of signals) {
    const text = signalText(s); if (!text) continue;
    let hits = 0; for (const t of titleTokens) if (text.includes(t)) hits++;
    const lexical = titleTokens.length ? hits / Math.min(14,titleTokens.length) : 0;
    const regionBoost = region && region !== 'monde' && text.includes(region) ? .2 : 0;
    const trust = clamp(s?.source_trust ?? .5,.2,1);
    const score = (lexical + regionBoost) * trust;
    if (score >= .16) matches.push({
      score:Number(score.toFixed(3)),title:s.title,source_key:s.source_key,source_label:s.source_label,
      source_family:s.source_family,source_trust:s.source_trust,url:s.url||'',observed_at:s.observed_at||s.event_at||null
    });
  }
  return matches.sort((a,b)=>b.score-a.score).slice(0,10);
}

function machineRuleVerdict(rule, signals = []) {
  if (!rule || typeof rule !== 'object') return null;
  if (rule.type === 'signal_event_type_present') {
    const wanted = new Set([].concat(rule.event_types || rule.event_type || []).map(String));
    const matches = signals.filter(s=>wanted.has(String(s.event_type)) && (!rule.geography || normalize(s.geography).includes(normalize(rule.geography))));
    if (matches.length >= Number(rule.minimum_matches || 1)) return {outcome:1,confidence:.99,evidence:matches.slice(0,8)};
  }
  if (rule.type === 'numeric_fact_threshold') {
    const matches=[];
    for(const s of signals){
      if(rule.source_key && String(s.source_key)!==String(rule.source_key)) continue;
      const value=Number(s?.facts?.[rule.fact]); if(!Number.isFinite(value)) continue;
      const threshold=Number(rule.threshold); let ok=false;
      if(rule.operator==='>=')ok=value>=threshold; else if(rule.operator==='>')ok=value>threshold; else if(rule.operator==='<=')ok=value<=threshold; else if(rule.operator==='<')ok=value<threshold;
      if(ok)matches.push(s);
    }
    if(matches.length) return {outcome:1,confidence:.995,evidence:matches.slice(0,8)};
  }
  return null;
}

export function buildResolutionAssessments(rows = [], signals = [], {now=Date.now()}={}) {
  const out=[];
  for(const row of rows){
    const target = row.target_at ? new Date(row.target_at).getTime() : NaN;
    if(!Number.isFinite(target) || target > now) continue;
    const meta=row.meta||{};
    const contract=meta.resolution_contract || resolutionContract(meta.forecast||meta);
    const machine=machineRuleVerdict(contract.machine_rule,signals);
    if(machine){
      out.push({scenario_key:row.scenario_key,status:'auto_resolved',outcome:machine.outcome,resolver:'machine_rule',confidence:machine.confidence,evidence:machine.evidence,note:'Résolution automatique fondée sur une règle machine explicitement publiée avec le scénario.',resolution_kind:contract.kind});
      continue;
    }
    const matches=evidenceMatches(row,signals);
    const families=new Set(matches.map(x=>x.source_family||x.source_key));
    const strong=matches.filter(x=>Number(x.score)>=.28 && Number(x.source_trust||0)>=.7);
    const suggestion=strong.length>=2 && families.size>=2 ? 'suggested_positive' : 'needs_review';
    out.push({
      scenario_key:row.scenario_key,status:suggestion,outcome:null,resolver:'evidence_assistant',
      confidence:suggestion==='suggested_positive'?Math.min(.9,.52+strong.length*.08+families.size*.05):Math.min(.65,.25+matches.length*.05),
      evidence:matches,note:suggestion==='suggested_positive'?'Plusieurs sources indépendantes recoupent le scénario, mais un humain ou une règle objective doit encore valider le verdict.':'Échéance atteinte : vérité terrain insuffisamment objective pour une résolution automatique.',resolution_kind:contract.kind
    });
  }
  return out;
}
