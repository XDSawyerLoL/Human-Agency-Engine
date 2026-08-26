const clampProbability = p => Math.max(0.001, Math.min(0.999, Number(p) || 0));
const round = (v, n=4) => Number.isFinite(Number(v)) ? Number(Number(v).toFixed(n)) : null;

export function isBinaryScorable(row) {
  if (![0,1].includes(Number(row?.outcome))) return false;
  const kind = String(row?.resolution_kind || row?.meta?.resolution_contract?.kind || 'binary_event').toLowerCase();
  return !['numeric','categorical','open_question','non_binary'].includes(kind);
}

export function scoreRows(rows = []) {
  const scorable = rows.filter(isBinaryScorable);
  if (!scorable.length) return {
    n:0,brier:null,log_loss:null,hit_rate:null,base_rate:null,baseline_brier:null,brier_skill_score:null,ece:null
  };
  const baseRate = scorable.reduce((a,r)=>a+Number(r.outcome),0) / scorable.length;
  let brier = 0, logLoss = 0, hits = 0, baseline = 0;
  for (const r of scorable) {
    const p = clampProbability(r.first_probability);
    const y = Number(r.outcome);
    brier += (p-y)**2;
    logLoss += -(y*Math.log(p)+(1-y)*Math.log(1-p));
    hits += ((p >= .5 ? 1 : 0) === y) ? 1 : 0;
    baseline += (baseRate-y)**2;
  }
  brier /= scorable.length;
  logLoss /= scorable.length;
  baseline /= scorable.length;
  const buckets = calibrationBuckets(scorable, 10);
  const ece = buckets.reduce((sum,b)=>sum + (b.n/scorable.length)*Math.abs((b.mean_probability??0)-(b.observed_frequency??0)),0);
  return {
    n:scorable.length,
    brier:round(brier),
    log_loss:round(logLoss),
    hit_rate:round(hits/scorable.length,4),
    base_rate:round(baseRate,4),
    baseline_brier:round(baseline),
    brier_skill_score:baseline>0?round(1-brier/baseline):null,
    ece:round(ece)
  };
}

export function calibrationBuckets(rows = [], step = 10) {
  const bins = [];
  for (let low=0; low<100; low+=step) {
    const high = low + step;
    const group = rows.filter(r => {
      const pct = clampProbability(r.first_probability)*100;
      return pct >= low && (high === 100 ? pct <= high : pct < high);
    });
    const meanP = group.length ? group.reduce((a,r)=>a+clampProbability(r.first_probability),0)/group.length : null;
    const observed = group.length ? group.reduce((a,r)=>a+Number(r.outcome),0)/group.length : null;
    bins.push({
      label:`${low}–${high}%`,low,high,n:group.length,
      mean_probability:round(meanP,4),observed_frequency:round(observed,4),
      calibration_gap:group.length?round(observed-meanP,4):null
    });
  }
  return bins;
}

function segment(rows, keyFn, minSamples=5) {
  const groups = new Map();
  for (const row of rows.filter(isBinaryScorable)) {
    const key = keyFn(row) || 'unknown';
    const arr = groups.get(key) || [];
    arr.push(row); groups.set(key,arr);
  }
  return [...groups.entries()].map(([key,group])=>({key,...scoreRows(group),ready:group.length>=minSamples})).sort((a,b)=>b.n-a.n || String(a.key).localeCompare(String(b.key)));
}

export function buildCalibrationReport(rows = [], {minimumGlobal=30, minimumSegment=8}={}) {
  const scorable = rows.filter(isBinaryScorable);
  const global = scoreRows(scorable);
  const byDomain = segment(scorable,r=>r.domain,minimumSegment);
  const byHorizon = segment(scorable,r=>r.horizon_tier,minimumSegment);
  const byOrigin = segment(scorable,r=>r.origin_group || r.resolution_origin || 'native',minimumSegment);
  const weights = [...byDomain].filter(x=>x.ready && x.brier!==null).map(x=>({
    domain:x.key,samples:x.n,brier:x.brier,
    suggested_reliability_weight:round(Math.max(.35,Math.min(1.35,1.15-(x.brier-.18)*1.8)),3),
    status:'shadow_only'
  }));
  return {
    generated_at:new Date().toISOString(),
    calibration_ready:global.n>=minimumGlobal,
    minimum_global_samples:minimumGlobal,
    minimum_segment_samples:minimumSegment,
    scorable_resolutions:global.n,
    global,
    buckets:calibrationBuckets(scorable,10),
    by_domain:byDomain,
    by_horizon:byHorizon,
    by_origin:byOrigin,
    shadow_weight_recommendations:weights,
    weights_applied_to_public_probability:false,
    methodology:'Brier, log loss, ECE and Brier skill score are calculated on the first published probability of objectively resolved binary forecasts only.'
  };
}
