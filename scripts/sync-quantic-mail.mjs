import {
  cpSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const work=mkdtempSync(join(tmpdir(),"quanticmail-dist-"));
const relayWork=mkdtempSync(join(tmpdir(),"quanticmail-relay-"));
const target=join(root,"public","mail");
const relayTarget=join(root,"vendor","quanticmail-relay");
const stage=join(root,"public",".mail-stage");

const REPO="https://github.com/XDSawyerLoL/QuanticMail.git";
const DIST_COMMIT="8aba3d5038f64911895041c2278502d932e4ba4a";
const SOURCE_COMMIT="e8ab65a082eab42a0b0fd43d1dce307262f3bf58";
const RELAY_SOURCE_COMMIT="fc1bafe8ea3da99f0f4218e23b4b34d882005f84";
const BOOTSTRAP_SENTINEL="https://quantic-hostinger-relay.invalid";
const RAILWAY_RELAY="https://quantic-network-relay-backup-production.up.railway.app";

function run(command,args,{cwd=root}={}){
  const result=spawnSync(command,args,{cwd,stdio:"inherit",shell:false});
  if(result.status!==0)throw new Error(`${command} ${args.join(" ")} a échoué (code ${result.status??"?"}).`);
}

function hostingerRelay(env=process.env){
  const candidate=String(env.QUANTIC_HOSTINGER_RELAY_URL||"").trim().replace(/\/$/,"");
  if(!candidate)return RAILWAY_RELAY;
  try{
    const url=new URL(candidate);
    if(url.protocol!=="https:"||url.username||url.password||url.search||url.hash){
      throw new Error("invalid");
    }
    return candidate;
  }catch{
    throw new Error("QUANTIC_HOSTINGER_RELAY_URL doit être une URL HTTPS publique sans identifiants, query ni fragment.");
  }
}

function syncRelaySource(){
  run("git",["init","--quiet"],{cwd:relayWork});
  run("git",["remote","add","origin",REPO],{cwd:relayWork});
  run("git",["fetch","--quiet","--depth","1","origin",RELAY_SOURCE_COMMIT],{cwd:relayWork});
  run("git",["checkout","--quiet","--detach","FETCH_HEAD"],{cwd:relayWork});

  for(const required of ["standalone-relay","lib"]){
    if(!existsSync(join(relayWork,required)))throw new Error(`Source Quantic Relay incomplète: ${required} absent.`);
  }

  rmSync(relayTarget,{recursive:true,force:true});
  mkdirSync(relayTarget,{recursive:true});
  cpSync(join(relayWork,"standalone-relay"),join(relayTarget,"standalone-relay"),{recursive:true});
  cpSync(join(relayWork,"lib"),join(relayTarget,"lib"),{recursive:true});
  writeFileSync(join(relayTarget,"QUANTICMAIL_RELAY_COMMIT"),`${RELAY_SOURCE_COMMIT}\n`,"utf8");
}

function patchSentinel(directory,replacement){
  let replacements=0;
  const sentinel=Buffer.from(BOOTSTRAP_SENTINEL,"utf8");

  function visit(current){
    for(const entry of readdirSync(current)){
      if(entry===".git")continue;
      const path=join(current,entry);
      const info=statSync(path);
      if(info.isDirectory()){
        visit(path);
        continue;
      }
      if(!info.isFile())continue;
      const raw=readFileSync(path);
      if(!raw.includes(sentinel))continue;
      const text=raw.toString("utf8");
      const matches=text.split(BOOTSTRAP_SENTINEL).length-1;
      if(matches<=0)continue;
      writeFileSync(path,text.split(BOOTSTRAP_SENTINEL).join(replacement),"utf8");
      replacements+=matches;
    }
  }

  visit(directory);
  return replacements;
}

try{
  run("git",["init","--quiet"],{cwd:work});
  run("git",["remote","add","origin",REPO],{cwd:work});
  run("git",["fetch","--quiet","--depth","1","origin",DIST_COMMIT],{cwd:work});
  run("git",["checkout","--quiet","--detach","FETCH_HEAD"],{cwd:work});

  const sourceManifest=readFileSync(join(work,"QUANTICMAIL_COMMIT"),"utf8").trim();
  if(sourceManifest!==SOURCE_COMMIT){
    throw new Error(`Distribution QuanticMail inattendue: ${sourceManifest||"manifeste vide"}.`);
  }

  for(const required of ["index.html",join("network","index.html"),join("vault","index.html")]){
    if(!existsSync(join(work,required)))throw new Error(`QuanticMail prebuilt incomplet: ${required} absent.`);
  }

  syncRelaySource();

  const relay=hostingerRelay(process.env);
  const replacements=patchSentinel(work,relay);
  if(replacements<1){
    throw new Error("La sentinelle de bootstrap QuanticMail est absente du bundle précompilé.");
  }

  rmSync(stage,{recursive:true,force:true});
  cpSync(work,stage,{
    recursive:true,
    filter:(source)=>!source.split(/[\\/]/).includes(".git"),
  });
  rmSync(target,{recursive:true,force:true});
  renameSync(stage,target);

  console.log(JSON.stringify({
    ok:true,
    product:"QuanticMail",
    distributionCommit:DIST_COMMIT,
    sourceCommit:SOURCE_COMMIT,
    target:"public/mail",
    basePath:"/mail",
    relayInjected:relay,
    replacements,
    relaySourceCommit:RELAY_SOURCE_COMMIT,
    relayVendor:"vendor/quanticmail-relay",
  }));
}finally{
  rmSync(stage,{recursive:true,force:true});
  rmSync(work,{recursive:true,force:true});
  rmSync(relayWork,{recursive:true,force:true});
}
