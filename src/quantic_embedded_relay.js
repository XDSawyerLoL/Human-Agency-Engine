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

export function installEmbeddedQuanticRelay(app){
  if(app.__embeddedQuanticRelayInstalled)return;
  app.__embeddedQuanticRelayInstalled=true;

  app.use(async(req,res,next)=>{
    const path=String(req.path||req.url||"").split("?",1)[0];
    if(!path.startsWith("/api/quantic/"))return next();

    try{
      const instance=await relay();
      if(!instance){
        res.status(503).json({
          error:"Quantic Relay Hostinger indisponible: persistance MySQL non configurée.",
        });
        return;
      }
      const handled=await instance.handle(req,res);
      if(!handled&&!res.headersSent&&!res.writableEnded)next();
    }catch(error){
      console.error("[quantic-relay]",error?.message||error);
      if(!res.headersSent){
        res.status(503).json({error:"Quantic Relay Hostinger temporairement indisponible."});
      }else if(!res.writableEnded){
        res.end();
      }
    }
  });
}
