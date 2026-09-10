import { buildCryptoForecast, cryptoCatalog } from '../src/crypto_market_forecast.js';

const now=Date.now();
const prices=[];const volumes=[];const klines=[];
for(let i=0;i<1000;i++){
  const t=now-(999-i)*3600000;
  const wave=Math.sin(i/17)*180+Math.cos(i/43)*90;
  const p=42000+i*8+wave;
  prices.push([t,p]);volumes.push([t,800_000_000+(i%24)*5_000_000]);
  klines.push([t,String(p-15),String(p+60),String(p-70),String(p*1.001),String(10),t+3599999,String(900_000_000),100,'5','450000000','0']);
}

globalThis.fetch=async url=>{
  const u=String(url);
  if(u.includes('coingecko.com'))return new Response(JSON.stringify({prices,market_caps:[],total_volumes:volumes}),{status:200,headers:{'content-type':'application/json'}});
  if(u.includes('api.binance.com'))return new Response(JSON.stringify(klines),{status:200,headers:{'content-type':'application/json'}});
  return new Response('{}',{status:404});
};

const out=await buildCryptoForecast('BTC');
if(out.schema!=='providence-crypto-forecast-v1')throw new Error('wrong crypto schema');
if(out.asset.symbol!=='BTC')throw new Error('wrong asset');
if(out.market.provider_count!==2)throw new Error('expected two independent market providers');
if(!Array.isArray(out.forecasts)||out.forecasts.length!==4)throw new Error('expected four forecast horizons');
for(const row of out.forecasts){
  const p=row.probability_percent;
  const total=p.up+p.range+p.down;
  if(total<99||total>101)throw new Error(`probability mass invalid for ${row.horizon}: ${total}`);
  if(!(row.range_80_percent[0]<row.median_price&&row.median_price<row.range_80_percent[1]))throw new Error(`invalid forecast range for ${row.horizon}`);
  if(!(row.confidence_percent>=0&&row.confidence_percent<=100))throw new Error('invalid confidence');
}
if(out.quality.score<50)throw new Error('cross-source quality unexpectedly low');
if(!cryptoCatalog().some(x=>x.symbol==='ETH'))throw new Error('ETH missing from catalog');
console.log(JSON.stringify({ok:true,asset:out.asset.symbol,providers:out.market.provider_count,horizons:out.forecasts.map(x=>x.horizon),quality:out.quality.score}));
