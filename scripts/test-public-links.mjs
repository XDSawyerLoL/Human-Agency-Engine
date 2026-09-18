import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve('public');
const htmlFiles=[];
function walk(dir){
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
    const full=path.join(dir,entry.name);
    if(entry.isDirectory()) walk(full);
    else if(entry.isFile()&&entry.name.endsWith('.html')) htmlFiles.push(full);
  }
}
walk(root);

const errors=[];
const normalizeHref=href=>href.split('#')[0].split('?')[0];
const existsRoute=href=>{
  const clean=normalizeHref(href);
  if(!clean||clean==='/') return fs.existsSync(path.join(root,'index.html'));
  const rel=clean.replace(/^\//,'');
  const direct=path.join(root,rel);
  if(fs.existsSync(direct)) return true;
  if(fs.existsSync(path.join(direct,'index.html'))) return true;
  return false;
};

for(const file of htmlFiles){
  const source=fs.readFileSync(file,'utf8');
  for(const match of source.matchAll(/href=["']([^"']+)["']/g)){
    const href=match[1].trim();
    if(!href){ errors.push(file+': href vide'); continue; }
    if(/^(https?:|mailto:|tel:|data:|javascript:)/i.test(href)) continue;
    if(href.startsWith('#')){
      const id=href.slice(1);
      if(id && !source.includes('id="'+id+'"') && !source.includes("id='"+id+"'") && !source.includes('name="'+id+'"') && !source.includes("name='"+id+"'")){
        errors.push(file+': ancre absente '+href);
      }
      continue;
    }
    if(href.startsWith('/') && !existsRoute(href)) errors.push(file+': route interne absente '+href);
  }
}

if(errors.length){
  console.error('Public link audit failed:');
  for(const error of errors) console.error(' -',error);
  process.exit(1);
}
console.log('Public link audit OK: '+htmlFiles.length+' pages HTML, aucune destination interne morte.');
