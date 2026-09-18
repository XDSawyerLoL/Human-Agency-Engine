import { cpSync, existsSync, mkdtempSync, renameSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const work=mkdtempSync(join(tmpdir(),"quanticmail-source-"));
const target=join(root,"public","mail");
const stage=join(root,"public",".mail-stage");
const REPO="https://github.com/XDSawyerLoL/QuanticMail.git";
const COMMIT="2e2a0a37ab7514e616739dd9f366cebdf107ff2e";
const DEFAULT_BOOTSTRAPS="https://quantic-network-relay-backup-production.up.railway.app";

function mailBootstraps(env=process.env){
  const values=[];
  const hostinger=String(env.QUANTIC_HOSTINGER_RELAY_URL||"").trim().replace(/\/$/,"");
  if(hostinger){
    try{ if(new URL(hostinger).protocol==="https:") values.push(hostinger); }catch{}
  }
  const configured=String(env.NEXT_PUBLIC_QUANTIC_BOOTSTRAPS||DEFAULT_BOOTSTRAPS)
    .split(",").map(value=>value.trim()).filter(Boolean);
  for(const value of configured){
    if(!values.includes(value))values.push(value);
  }
  return values.join(",");
}

function run(command,args,{cwd=root,env=process.env}={}){
  const result=spawnSync(command,args,{cwd,env,stdio:"inherit",shell:false});
  if(result.status!==0)throw new Error(`${command} ${args.join(" ")} a échoué (code ${result.status??"?"}).`);
}

try{
  run("git",["init","--quiet"],{cwd:work});
  run("git",["remote","add","origin",REPO],{cwd:work});
  run("git",["fetch","--quiet","--depth","1","origin",COMMIT],{cwd:work});
  run("git",["checkout","--quiet","--detach","FETCH_HEAD"],{cwd:work});
  run("npm",["install","--ignore-scripts","--no-audit","--no-fund"],{cwd:work});
  run("npm",["run","build:hostinger"],{
    cwd:work,
    env:{
      ...process.env,
      NEXT_PUBLIC_QUANTIC_BOOTSTRAPS:mailBootstraps(process.env)
    }
  });
  const built=join(work,"out");
  for(const required of ["index.html",join("network","index.html"),join("vault","index.html")]){
    if(!existsSync(join(built,required)))throw new Error(`QuanticMail export incomplet: ${required} absent.`);
  }
  rmSync(stage,{recursive:true,force:true});
  cpSync(built,stage,{recursive:true});
  rmSync(target,{recursive:true,force:true});
  renameSync(stage,target);
  console.log(JSON.stringify({ok:true,product:"QuanticMail",commit:COMMIT,target:"public/mail",basePath:"/mail"}));
}finally{
  rmSync(stage,{recursive:true,force:true});
  rmSync(work,{recursive:true,force:true});
}
