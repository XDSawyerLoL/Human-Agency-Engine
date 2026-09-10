const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=6)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;

export const CRYPTO_ASSETS={
  BTC:{symbol:'BTC',name:'Bitcoin',coingecko_id:'bitcoin',binance_symbol:'BTCUSDT'},
  ETH:{symbol:'ETH',name:'Ethereum',coingecko_id:'ethereum',binance_symbol:'ETHUSDT'},
  SOL:{symbol:'SOL',name:'Solana',coingecko_id:'solana',binance_symbol:'SOLUSDT'},
  XRP:{symbol:'XRP',name:'XRP',coingecko_id:'ripple',binance_symbol:'XRPUSDT'},
  BNB:{symbol:'BNB',name:'BNB',coingecko_id:'binancecoin',binance_symbol:'BNBUSDT'},
  ADA:{symbol:'ADA',name:'Cardano',coingecko_id:'cardano',binance_symbol:'ADAUSDT'},
  DOGE:{symbol:'DOGE',name:'Dogecoin',coingecko_id:'dogecoin',binance_symbol:'DOGEUSDT'},
  AVAX:{symbol:'AVAX',name:'Avalanche',coingecko_id:'avalanche-2',binance_symbol:'AVAXUSDT'},
  LINK:{symbol:'LINK',name:'Chainlink',coingecko_id:'chainlink',binance_symbol:'LINKUSDT'},
  DOT:{symbol:'DOT',name:'Polkadot',coingecko_id:'polkadot',binance_symbol:'DOTUSDT'},
  LTC:{symbol:'LTC',name:'Litecoin',coingecko_id:'litecoin',binance_symbol:'LTCUSDT'}
};

const HORIZONS=[
  {key:'1h',label:'1 heure',hours:1,drift_windows:[1,6,24],weights:[.5,.32,.18]},
  {key:'24h',label:'24 heures',hours:24,drift_windows:[6,24,168],weights:[.22,.48,.30]},
  {key:'7d',label:'7 jours',hours:168,drift_windows:[24,168,720],weights:[.15,.50,.35]},
  {key:'30d',label:'30 jours',hours:720,drift_windows:[168,720],weights:[.40,.60]}
];

function safeLog(v){return Math.log(Math.max(1e-12,Number(v)||1e-12));}
function mean(values){const rows=values.filter(Number.isFinite);return rows.length?rows.reduce((a,b)=>a+b,0)/rows.length:null;}
function std(values){const rows=values.filter(Number.isFinite);if(rows.length<2)return null;const m=mean(rows);return Math.sqrt(rows.reduce((a,b)=>a+(b-m)**2,0)/(rows.length-1));}
function pctChange(a,b){return Number(a)>0&&Number(b)>0?(Number(b)/Number(a)-1):null;}
function erf(x){const sign=x<0?-1:1;const a=Math.abs(x);const t=1/(1+.3275911*a);const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-a*a);return sign*y;}
function normalCdf(x){return .5*(1+erf(x/Math.sqrt(2)));}
function logistic(x){return 1/(1+Math.exp(-x));}

function normalizeAsset(input){
  const raw=String(input||'BTC').trim().toUpperCase();
  if(CRYPTO_ASSETS[raw])return CRYPTO_ASSETS[raw];
  return Object.values(CRYPTO_ASSETS).find(x=>x.name.toUpperCase()===raw||x.coingecko_id.toUpperCase()===raw)||null;
}

async function fetchJson(url,{headers={},timeoutMs=8000}={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const response=await fetch(url,{headers:{accept:'application/json','user-agent':'Providence/1.19',...headers},signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }finally{clearTimeout(timer);}
}

async function fetchCoinGecko(asset,currency){
  const key=String(process.env.COINGECKO_API_KEY||process.env.CG_DEMO_API_KEY||'').trim();
  const base=key&&process.env.COINGECKO_PRO==='1'?'https://pro-api.coingecko.com/api/v3':'https://api.coingecko.com/api/v3';
  const headers=key?{[process.env.COINGECKO_PRO==='1'?'x-cg-pro-api-key':'x-cg-demo-api-key']:key}:{};
  const qs=new URLSearchParams({vs_currency:currency,days:'45',interval:'hourly',precision:'full'});
  const data=await fetchJson(`${base}/coins/${encodeURIComponent(asset.coingecko_id)}/market_chart?${qs}`,{headers});
  const prices=(data.prices||[]).map(row=>({t:Number(row[0]),p:Number(row[1])})).filter(x=>Number.isFinite(x.t)&&x.p>0);
  const volumes=(data.total_volumes||[]).map(row=>({t:Number(row[0]),v:Number(row[1])})).filter(x=>Number.isFinite(x.t)&&Number.isFinite(x.v));
  if(prices.length<48)throw new Error('coingecko_insufficient_history');
  return {provider:'CoinGecko',prices,volumes,latest:prices.at(-1)?.p||null,updated_at:new Date(prices.at(-1).t).toISOString()};
}

async function fetchBinance(asset,currency){
  if(currency!=='usd')throw new Error('binance_usd_only');
  const data=await fetchJson(`https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(asset.binance_symbol)}&interval=1h&limit=1000`);
  const prices=(Array.isArray(data)?data:[]).map(row=>({t:Number(row[0]),p:Number(row[4])})).filter(x=>Number.isFinite(x.t)&&x.p>0);
  const volumes=(Array.isArray(data)?data:[]).map(row=>({t:Number(row[0]),v:Number(row[7])})).filter(x=>Number.isFinite(x.t)&&Number.isFinite(x.v));
  if(prices.length<48)throw new Error('binance_insufficient_history');
  return {provider:'Binance',prices,volumes,latest:prices.at(-1)?.p||null,updated_at:new Date(prices.at(-1).t).toISOString()};
}

function nearestPrice(series,hoursAgo){
  if(!series.length)return null;
  const target=series.at(-1).t-hoursAgo*3600000;
  let best=series[0],gap=Math.abs(series[0].t-target);
  for(const item of series){const g=Math.abs(item.t-target);if(g<gap){best=item;gap=g;}}
  return best?.p||null;
}

function ema(values,period){
  const rows=values.filter(Number.isFinite);if(!rows.length)return null;
  const k=2/(period+1);let out=rows[0];for(let i=1;i<rows.length;i++)out=rows[i]*k+out*(1-k);return out;
}

function rsi(values,period=14){
  const rows=values.filter(Number.isFinite);if(rows.length<period+1)return null;
  let gains=0,losses=0;
  for(let i=rows.length-period;i<rows.length;i++){const d=rows[i]-rows[i-1];if(d>=0)gains+=d;else losses-=d;}
  if(losses===0)return 100;const rs=(gains/period)/(losses/period);return 100-(100/(1+rs));
}

function marketMetrics(series,volumes=[]){
  const prices=series.map(x=>x.p),latest=prices.at(-1);
  const logReturns=[];for(let i=1;i<prices.length;i++)logReturns.push(safeLog(prices[i]/prices[i-1]));
  const vol1h=std(logReturns.slice(-168))||std(logReturns)||0;
  const change={};for(const h of [1,6,24,168,720])change[h]=pctChange(nearestPrice(series,h),latest);
  const e12=ema(prices.slice(-80),12),e26=ema(prices.slice(-120),26);
  const emaSpread=e12&&e26?e12/e26-1:0;
  const rsi14=rsi(prices,14);
  const max30=Math.max(...prices.slice(-Math.min(720,prices.length)));
  const drawdown30=max30>0?latest/max30-1:0;
  const recentVolume=mean(volumes.slice(-24).map(x=>x.v));
  const priorVolume=mean(volumes.slice(-48,-24).map(x=>x.v));
  const volumeRatio=recentVolume&&priorVolume?recentVolume/priorVolume:null;
  return {latest,logReturns,vol1h,change,ema_spread:emaSpread,rsi14,drawdown30,volume_ratio_24h:volumeRatio};
}

function weightedDrift(metrics,horizon){
  let sum=0,total=0;
  horizon.drift_windows.forEach((window,index)=>{
    const raw=metrics.change[window];if(!Number.isFinite(raw))return;
    const hours=Math.max(1,window),hourly=safeLog(1+raw)/hours;
    const w=horizon.weights[index]||0;sum+=hourly*w;total+=w;
  });
  let drift=total?sum/total:0;
  const trend=Math.tanh((metrics.ema_spread||0)/Math.max(.002,metrics.vol1h*5));
  drift+=trend*metrics.vol1h*.045;
  if(Number.isFinite(metrics.rsi14))drift+=clamp((metrics.rsi14-50)/50,-1,1)*metrics.vol1h*.015;
  // Shrink noisy extrapolation aggressively. Providence predicts a distribution,
  // not a straight-line continuation of recent returns.
  return drift*.42;
}

function horizonForecast(metrics,horizon,sourceQuality){
  const sigma=Math.max(.001,metrics.vol1h*Math.sqrt(horizon.hours));
  const rawMean=weightedDrift(metrics,horizon)*horizon.hours;
  const meanLogReturn=clamp(rawMean,-sigma*.85,sigma*.85);
  const neutralBand=Math.max(.0025,sigma*.28);
  const pDown=normalCdf((-neutralBand-meanLogReturn)/sigma);
  const pUp=1-normalCdf((neutralBand-meanLogReturn)/sigma);
  const pFlat=clamp(1-pUp-pDown,0,1);
  const total=pUp+pDown+pFlat||1;
  const probs={up:pUp/total,flat:pFlat/total,down:pDown/total};
  const z80=1.281551565545;
  const median=metrics.latest*Math.exp(meanLogReturn);
  const low=metrics.latest*Math.exp(meanLogReturn-z80*sigma);
  const high=metrics.latest*Math.exp(meanLogReturn+z80*sigma);
  const directionalEdge=Math.abs(probs.up-probs.down);
  const confidence=clamp(28+sourceQuality*42+directionalEdge*24-Math.min(18,sigma*55),18,92);
  const direction=probs.up>probs.down&&probs.up>probs.flat?'up':probs.down>probs.up&&probs.down>probs.flat?'down':'range';
  return {
    horizon:horizon.key,label:horizon.label,direction,
    probability_percent:{up:Math.round(probs.up*100),range:Math.round(probs.flat*100),down:Math.round(probs.down*100)},
    median_price:round(median,8),range_80_percent:[round(low,8),round(high,8)],
    expected_return_percent:round((Math.exp(meanLogReturn)-1)*100,2),
    modeled_volatility_percent:round(sigma*100,2),confidence_percent:Math.round(confidence)
  };
}

function sourceConsensus(sources){
  const values=sources.map(x=>x.latest).filter(x=>Number.isFinite(x)&&x>0);
  if(!values.length)return {consensus_price:null,disagreement_percent:null,quality:0};
  const consensus=mean(values);
  const maxDeviation=Math.max(...values.map(v=>Math.abs(v-consensus)/consensus));
  const recency=sources.filter(x=>Date.now()-Date.parse(x.updated_at)<3*3600000).length/Math.max(1,sources.length);
  const quality=clamp(.45+.22*Math.min(1,sources.length/2)+.25*recency-.55*maxDeviation,.15,.98);
  return {consensus_price:consensus,disagreement_percent:maxDeviation*100,quality};
}

export async function buildCryptoForecast(assetInput='BTC',{currency='usd'}={}){
  const asset=normalizeAsset(assetInput);if(!asset)throw new Error('unsupported_crypto_asset');
  const c=String(currency||'usd').trim().toLowerCase();
  const attempts=await Promise.allSettled([fetchCoinGecko(asset,c),fetchBinance(asset,c)]);
  const sources=attempts.filter(x=>x.status==='fulfilled').map(x=>x.value);
  const errors=attempts.filter(x=>x.status==='rejected').map(x=>String(x.reason?.message||x.reason));
  if(!sources.length)throw new Error(`crypto_market_data_unavailable:${errors.join('|')}`);
  const primary=[...sources].sort((a,b)=>b.prices.length-a.prices.length)[0];
  const metrics=marketMetrics(primary.prices,primary.volumes);
  const consensus=sourceConsensus(sources);
  const effectiveLatest=consensus.consensus_price||metrics.latest;
  metrics.latest=effectiveLatest;
  const forecasts=HORIZONS.map(h=>horizonForecast(metrics,h,consensus.quality));
  const latestDirection=forecasts.find(x=>x.horizon==='24h')?.direction||'range';
  const regimeScore=clamp(
    ((metrics.change[24]||0)/Math.max(.01,metrics.vol1h*Math.sqrt(24)))*.35+
    ((metrics.change[168]||0)/Math.max(.02,metrics.vol1h*Math.sqrt(168)))*.35+
    Math.tanh((metrics.ema_spread||0)/Math.max(.003,metrics.vol1h*6))*.30,
    -1,1
  );
  return {
    schema:'providence-crypto-forecast-v1',engine:'providence-crypto-market-v1',generated_at:new Date().toISOString(),
    asset:{symbol:asset.symbol,name:asset.name,currency:c.toUpperCase()},
    market:{price:round(effectiveLatest,8),provider_count:sources.length,providers:sources.map(x=>({name:x.provider,latest_price:round(x.latest,8),updated_at:x.updated_at})),source_disagreement_percent:round(consensus.disagreement_percent,3)},
    regime:{state:regimeScore>.24?'bullish':regimeScore<-.24?'bearish':'mixed',score:round(regimeScore,3),next_24h_direction:latestDirection},
    indicators:{
      return_1h_percent:round((metrics.change[1]||0)*100,2),return_6h_percent:round((metrics.change[6]||0)*100,2),return_24h_percent:round((metrics.change[24]||0)*100,2),return_7d_percent:round((metrics.change[168]||0)*100,2),return_30d_percent:round((metrics.change[720]||0)*100,2),
      rsi_14h:round(metrics.rsi14,2),ema_12_26_spread_percent:round((metrics.ema_spread||0)*100,3),drawdown_30d_percent:round((metrics.drawdown30||0)*100,2),volume_ratio_24h:round(metrics.volume_ratio_24h,3),realized_volatility_1h_percent:round(metrics.vol1h*100,3)
    },
    forecasts,
    quality:{score:Math.round(consensus.quality*100),data_points:primary.prices.length,source_count:sources.length,cross_source_check:sources.length>1,errors},
    semantics:{
      probabilities_are_model_estimates:true,price_range_is_model_distribution:true,range_confidence_level:0.80,
      forecasts_are_not_guarantees:true,not_investment_advice:true,automatic_trade_execution:false,
      method:'multi-horizon log-return drift with aggressive shrinkage, realized-volatility distribution and cross-source price consensus'
    }
  };
}

export function cryptoCatalog(){return Object.values(CRYPTO_ASSETS).map(x=>({symbol:x.symbol,name:x.name,id:x.coingecko_id}));}
