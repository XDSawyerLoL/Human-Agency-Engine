import { buildCryptoForecast, cryptoCatalog } from './crypto_market_forecast.js';

const cache=new Map();
const TTL_MS=60_000;

function cacheKey(asset,currency){return `${String(asset||'BTC').toUpperCase()}:${String(currency||'usd').toLowerCase()}`;}

export function installCryptoMarketRoutes(app){
  if(app.__providenceCryptoMarketRoutesInstalled)return;
  app.__providenceCryptoMarketRoutesInstalled=true;

  app.get('/api/markets/crypto/catalog',(_req,res)=>{
    res.set('Cache-Control','public, max-age=300, stale-while-revalidate=900');
    res.json({schema:'providence-crypto-catalog-v1',assets:cryptoCatalog()});
  });

  app.get('/api/markets/crypto/forecast',async(req,res)=>{
    res.set('Cache-Control','public, max-age=30, stale-while-revalidate=90');
    const asset=String(req.query.asset||req.query.symbol||'BTC').trim();
    const currency=String(req.query.currency||'usd').trim().toLowerCase();
    const key=cacheKey(asset,currency),now=Date.now(),hit=cache.get(key);
    if(hit&&now-hit.at<TTL_MS)return res.json({...hit.value,cache:{hit:true,age_seconds:Math.round((now-hit.at)/1000),ttl_seconds:TTL_MS/1000}});
    try{
      const value=await buildCryptoForecast(asset,{currency});
      cache.set(key,{at:now,value});
      res.json({...value,cache:{hit:false,age_seconds:0,ttl_seconds:TTL_MS/1000}});
    }catch(error){
      if(hit)return res.status(206).json({...hit.value,cache:{hit:true,stale:true,age_seconds:Math.round((now-hit.at)/1000),ttl_seconds:TTL_MS/1000},warning:String(error?.message||error)});
      const message=String(error?.message||error);
      res.status(message.includes('unsupported_crypto_asset')?400:503).json({schema:'providence-crypto-forecast-v1',status:'unavailable',error:message});
    }
  });
}
