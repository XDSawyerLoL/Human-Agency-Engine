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
const DIST_COMMIT="5891f79e3f7c0e70678eb8a50d925a32d61c4420";
const SOURCE_COMMIT="46794c67ec5729cb368b390f0690c2cf220f7016";
const RELAY_SOURCE_COMMIT="46794c67ec5729cb368b390f0690c2cf220f7016";
const BOOTSTRAP_SENTINEL="https://quantic-hostinger-relay.invalid";
const RAILWAY_RELAY="https://quantic-network-relay-backup-production.up.railway.app";
const LEGACY_PORTAL_ORIGIN="https://mediumorchid-badger-314305.hostingersite.com";

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

function injectIdentityGate(directory){
  const scripts='<script src="/quantic-id-runtime.js"></script><script src="/quantic-mail-id-gate.js"></script>';
  let injected=0;
  function visit(current){
    for(const entry of readdirSync(current)){
      if(entry===".git")continue;
      const filePath=join(current,entry);
      const info=statSync(filePath);
      if(info.isDirectory()){visit(filePath);continue;}
      if(!info.isFile()||!filePath.endsWith(".html"))continue;
      const text=readFileSync(filePath,"utf8");
      if(text.includes("quantic-mail-id-gate.js"))continue;
      if(!text.includes("<head>"))continue;
      writeFileSync(filePath,text.replace("<head>","<head>"+scripts),"utf8");
      injected+=1;
    }
  }
  visit(directory);
  return injected;
}

function injectMailTheme(directory){
  const stylesheet='<link rel="stylesheet" href="/quantic-mail-v7.css?v=7.0">';
  let injected=0;
  function visit(current){
    for(const entry of readdirSync(current)){
      if(entry===".git")continue;
      const filePath=join(current,entry);
      const info=statSync(filePath);
      if(info.isDirectory()){visit(filePath);continue;}
      if(!info.isFile()||!filePath.endsWith(".html"))continue;
      const text=readFileSync(filePath,"utf8");
      if(text.includes("quantic-mail-v7.css"))continue;
      if(!text.includes("</head>"))continue;
      writeFileSync(filePath,text.replace("</head>",stylesheet+"</head>"),"utf8");
      injected+=1;
    }
  }
  visit(directory);
  return injected;
}

function makePortalUrlsPortable(directory){
  let patched=0;
  const routes=["/vision/","/mail/","/pulse/","/network/","/products/","/downloads/","/quantic/"];
  function visit(current){
    for(const entry of readdirSync(current)){
      if(entry===".git")continue;
      const filePath=join(current,entry);
      const info=statSync(filePath);
      if(info.isDirectory()){visit(filePath);continue;}
      if(!info.isFile()||!filePath.endsWith(".html"))continue;
      let text=readFileSync(filePath,"utf8");
      const before=text;
      for(const route of routes)text=text.split(LEGACY_PORTAL_ORIGIN+route).join(route);
      text=text.split(LEGACY_PORTAL_ORIGIN).join("/");
      text=text.split("Vérification du manifeste…").join("Quantic ID requis.");
      text=text.split("Préparation de Quantic Mail…").join("Quantic ID requis.");
      text=text.split("QuanticMail compare l’état local avec l’autorité disponible avant d’ouvrir la session.").join("Quantic Mail s’ouvre automatiquement dès qu’Identity Vault est détecté et qu’une identité est active sur cet appareil.");
      text=text.split("Quantic Mail vérifie votre identité et la disponibilité du service avant d’ouvrir la messagerie.").join("Quantic Mail s’ouvre automatiquement dès qu’Identity Vault est détecté et qu’une identité est active sur cet appareil.");
      if(filePath===join(directory,"index.html")&&text.includes("qn-onboarding-card")&&!text.includes("data-qm-static-actions")){
        text=text.replace("</p></section></main>",'</p><div class="qn-recovery-actions" data-qm-static-actions><a class="primary" href="/downloads/#identity-vault">Installer Identity Vault</a><button type="button" onclick="location.reload()">Réessayer</button><a href="/quantic/">Ouvrir Quantic ID</a></div></section></main>');
      }
      text=text.split('<a href="/vision/">Vision</a><a class="active" aria-current="page" href="/mail/">Mail</a><a href="/pulse/">Pulse</a><a href="/network/">Network</a><a href="/products/">Produits</a><a href="/downloads/">Téléchargements</a>').join('<a href="/vision/">Vision</a><a class="active" aria-current="page" href="/mail/">Mail</a><a href="/pulse/">Pulse</a><a href="/news/">News</a><a href="/network/">Network</a><a href="/products/">Produits</a><a href="/downloads/">Téléchargements</a>');
      if(text!==before){writeFileSync(filePath,text,"utf8");patched+=1;}
    }
  }
  visit(directory);
  return patched;
}

function injectMailResilience(directory){
  const script='<script src="/quantic-mail-resilience.js?v=1.0" defer></script>';
  let injected=0;
  function visit(current){
    for(const entry of readdirSync(current)){
      if(entry===".git")continue;
      const filePath=join(current,entry);
      const info=statSync(filePath);
      if(info.isDirectory()){visit(filePath);continue;}
      if(!info.isFile()||!filePath.endsWith(".html"))continue;
      const text=readFileSync(filePath,"utf8");
      if(text.includes("quantic-mail-resilience.js"))continue;
      if(!text.includes("</body>"))continue;
      writeFileSync(filePath,text.replace("</body>",script+"</body>"),"utf8");
      injected+=1;
    }
  }
  visit(directory);
  return injected;
}

function injectPortalNav(directory){
  const script='<script src="/quantic-mail-portal-nav.js" defer></script>';
  let injected=0;

  function visit(current){
    for(const entry of readdirSync(current)){
      if(entry===".git")continue;
      const filePath=join(current,entry);
      const info=statSync(filePath);
      if(info.isDirectory()){
        visit(filePath);
        continue;
      }
      if(!info.isFile()||!filePath.endsWith(".html"))continue;
      const text=readFileSync(filePath,"utf8");
      if(text.includes("quantic-mail-portal-nav.js"))continue;
      if(!text.includes("</body>"))continue;
      writeFileSync(filePath,text.replace("</body>",script+"</body>"),"utf8");
      injected+=1;
    }
  }

  visit(directory);
  return injected;
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

  const identityGatePages=injectIdentityGate(work);
  if(identityGatePages<3){
    throw new Error(`Verrou Quantic ID non injecté dans assez de pages Mail: ${identityGatePages}.`);
  }

  const mailThemePages=injectMailTheme(work);
  if(mailThemePages<3){
    throw new Error(`Thème Quantic Mail V7 non injecté dans assez de pages: ${mailThemePages}.`);
  }

  const portablePortalPages=makePortalUrlsPortable(work);
  if(portablePortalPages<1){
    throw new Error("Les URLs Quantic Mail n’ont pas été rendues portables.");
  }

  const portalNavPages=injectPortalNav(work);
  if(portalNavPages<3){
    throw new Error(`Navigation Quantic non injectée dans assez de pages Mail: ${portalNavPages}.`);
  }

  const resiliencePages=injectMailResilience(work);
  if(resiliencePages<3){
    throw new Error(`Résilience de chargement non injectée dans assez de pages Mail: ${resiliencePages}.`);
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
    identityGatePages,
    mailThemePages,
    portalNavPages,
    portablePortalPages,
    resiliencePages,
    relaySourceCommit:RELAY_SOURCE_COMMIT,
    relayVendor:"vendor/quanticmail-relay",
  }));
}finally{
  rmSync(stage,{recursive:true,force:true});
  rmSync(work,{recursive:true,force:true});
  rmSync(relayWork,{recursive:true,force:true});
}
