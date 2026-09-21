import { createHash } from "node:crypto";

import { config } from "./config.js";

const DEFAULT_PUBLIC_ORIGIN="https://mediumorchid-badger-314305.hostingersite.com";
const DEFAULT_BOOTSTRAPS=[
  "https://quanticmail-network-relay.onrender.com",
  "https://quantic-network-relay-backup-production.up.railway.app",
];

let relayPromise=null;

function parseMysqlUrl(env){
  const raw=String(env.MYSQL_URL||env.DATABASE_URL||"").trim();
  if(!raw)return null;
  try{
    const url=new URL(raw);
    if(!["mysql:","mariadb:"].includes(url.protocol))return null;
    return {
      host:url.hostname,
      port:Number.parseInt(url.port||"3306",10)||3306,
      user:decodeURIComponent(url.username||""),
      password:decodeURIComponent(url.password||""),
      database:decodeURIComponent(String(url.pathname||"").replace(/^\//,"")),
    };
  }catch{return null;}
}

function mysqlSettingsFromEnv(env=process.env){
  const fromUrl=parseMysqlUrl(env);
  const host=String(env.MYSQL_HOST||env.DB_HOST||fromUrl?.host||"").trim();
  const user=String(env.MYSQL_USER||env.DB_USER||fromUrl?.user||"").trim();
  const database=String(env.MYSQL_DATABASE||env.DB_NAME||fromUrl?.database||"").trim();
  const password=String(env.MYSQL_PASSWORD||env.DB_PASSWORD||fromUrl?.password||"");
  const rawPort=String(env.MYSQL_PORT||env.DB_PORT||fromUrl?.port||"3306");
  const port=Math.max(1,Math.min(65535,Number.parseInt(rawPort,10)||3306));
  return {host,user,database,password,port};
}

function publicEndpoint(env=process.env){
  const raw=String(
    env.QUANTIC_RELAY_PUBLIC_ENDPOINT||
    env.QUANTIC_PUBLIC_ORIGIN||
    DEFAULT_PUBLIC_ORIGIN
  ).trim().replace(/\/$/,"");
  try{
    const url=new URL(raw);
    if(url.protocol!=="https:"||url.username||url.password||url.search||url.hash)return null;
    return raw;
  }catch{return null;}
}

function identitySecret(env=process.env){
  const explicit=String(env.QUANTIC_RELAY_IDENTITY_SECRET||"").trim();
  if(explicit){
    if(explicit.length<32)throw new Error("QUANTIC_RELAY_IDENTITY_SECRET doit contenir au moins 32 caractères.");
    return explicit;
  }
  const mysql=mysqlSettingsFromEnv(env);
  const seed=String(
    env.EVIDENCE_ADMIN_KEY||
    mysql.password||
    env.MYSQL_URL||
    env.DATABASE_URL||
    ""
  );
  if(!seed)return null;
  return createHash("sha256")
    .update("quantic-hostinger-embedded-relay-v1\0")
    .update(seed)
    .digest("hex");
}

export function embeddedRelayConfiguration(env=process.env){
  const mysql=mysqlSettingsFromEnv(env);
  const endpoint=publicEndpoint(env);
  let secret=null;
  try{secret=identitySecret(env);}catch{return null;}
  if(!mysql.host||!mysql.user||!mysql.database||!secret||!endpoint)return null;
  return {
    mysql,
    identitySecret:secret,
    publicEndpoint:endpoint,
    bootstrapEndpoints:DEFAULT_BOOTSTRAPS,
  };
}

export function embeddedRelayPublicEndpoint(env=process.env){
  return embeddedRelayConfiguration(env)?.publicEndpoint??null;
}

async function createRelay(){
  const settings=embeddedRelayConfiguration(process.env);
  if(!settings)return null;

  const [{createMySqlRelayPersistenceFromConfig},{createEmbeddedRelay}]=await Promise.all([
    import("../vendor/quanticmail-relay/standalone-relay/mysql-storage.ts"),
    import("../vendor/quanticmail-relay/standalone-relay/embedded.ts"),
  ]);

  const persistence=await createMySqlRelayPersistenceFromConfig(
    settings.mysql,
    {identitySecret:settings.identitySecret},
  );
  const relay=await createEmbeddedRelay({
    persistence,
    publicEndpoint:settings.publicEndpoint,
    bootstrapEndpoints:settings.bootstrapEndpoints,
  });
  console.log(JSON.stringify({
    event:"quantic_relay_ready",
    relayId:relay.relayId,
    publicEndpoint:settings.publicEndpoint,
    persistence:"mysql",
  }));
  return relay;
}

async function relay(){
  if(!relayPromise){
    relayPromise=createRelay().catch(error=>{
      relayPromise=null;
      throw error;
    });
  }
  return relayPromise;
}
async function proxyToDurableRelay(req,res){
  const base=String(process.env.QUANTIC_RELAY_FALLBACK_ENDPOINT||DEFAULT_BOOTSTRAPS[0]||"").trim().replace(/\/$/,"");
  if(!base)throw new Error("Aucun relais Quantic durable de secours configuré.");
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),12_000);
  try{
    const method=String(req.method||"GET").toUpperCase();
    let body;
    if(!["GET","HEAD"].includes(method)){
      const chunks=[];
      let size=0;
      for await(const chunk of req){
        const buffer=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);
        size+=buffer.length;
        if(size>512*1024)throw Object.assign(new Error("Corps Quantic trop volumineux."),{status:413});
        chunks.push(buffer);
      }
      body=chunks.length?Buffer.concat(chunks):undefined;
    }
    const target=new URL(req.originalUrl||req.url||"/",base);
    const response=await fetch(target,{
      method,
      redirect:"error",
      cache:"no-store",
      signal:controller.signal,
      headers:{
        accept:String(req.headers.accept||"application/json"),
        ...(req.headers.authorization?{authorization:String(req.headers.authorization)}:{}),
        ...(req.headers["content-type"]?{"content-type":String(req.headers["content-type"])}:{})
      },
      body
    });
    const payload=Buffer.from(await response.arrayBuffer());
    res.status(response.status);
    res.set("Content-Type",response.headers.get("content-type")||"application/json; charset=utf-8");
    res.set("Cache-Control","no-store");
    res.set("X-Quantic-Relay-Backend","durable-fallback");
    res.send(payload);
    return true;
  }finally{
    clearTimeout(timer);
  }
}


export function installEmbeddedQuanticRelay(app){
  if(app.__embeddedQuanticRelayInstalled)return;
  app.__embeddedQuanticRelayInstalled=true;

  app.use(async(req,res,next)=>{
    const path=String(req.path||req.url||"").split("?",1)[0];
    if(!path.startsWith("/api/quantic/"))return next();

    try{
      const instance=await relay();
      if(!instance){
        await proxyToDurableRelay(req,res);
        return;
      }
      const handled=await instance.handle(req,res);
      if(!handled&&!res.headersSent&&!res.writableEnded)next();
    }catch(error){
      console.error("[quantic-relay]",error?.message||error);
      if(!res.headersSent){
        try{
          await proxyToDurableRelay(req,res);
        }catch(fallbackError){
          console.error("[quantic-relay-fallback]",fallbackError?.message||fallbackError);
          if(!res.headersSent)res.status(fallbackError?.status||503).json({error:"Quantic Relay temporairement indisponible."});
        }
      }else if(!res.writableEnded){
        res.end();
      }
    }
  });
}
