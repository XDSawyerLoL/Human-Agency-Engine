import fs from 'node:fs';

const pages=[
  ['home','public/index.html'],['predictions','public/predictions/index.html'],['horizons','public/horizons/index.html'],['causal','public/causal/index.html'],['sports','public/sports/index.html'],['intelligence','public/intelligence/index.html'],['track-record','public/track-record/index.html'],['modules','public/modules/index.html'],['sources','public/sources/index.html'],['cameras','public/cameras/index.html']
];
for(const [name,file] of pages){
  const html=fs.readFileSync(file,'utf8');
  if(!html.includes('providence-atmosphere.js'))throw new Error(`${name}: missing Providence shell loader`);
  if(name!=='home'&&!html.includes(`data-page="${name}"`))throw new Error(`${name}: missing data-page theme`);
}
const css=fs.readFileSync('public/providence-v12.css','utf8');
const fix=fs.readFileSync('public/providence-v12-1.css','utf8');
const art=fs.readFileSync('public/providence-v12-1-art.css','utf8');
const js=fs.readFileSync('public/providence-atmosphere.js','utf8');
for(const token of ['.pv12-sidebar','.pv12-scene','data-pv12-theme','fixture-card','graph-stage'])if(!css.includes(token))throw new Error(`V12 CSS missing ${token}`);
for(const token of ['providence-v12-1.css','providence-v12-1-art.css','document.querySelectorAll(\'.v4-nav,.topbar nav\')','Vue d’ensemble','Prédictions','Horizons','Causal World','Sports Calibration','Décision Intelligence','Track Record','Modules & Modèles','Sources & Données','Monde en direct','pv12-hero-visual'])if(!js.includes(token))throw new Error(`V12.1 shell JS missing ${token}`);
for(const token of ['.v4-horizon-jump','position:relative!important','width:auto!important','.fixture-probs>div:nth-child(1)'])if(!fix.includes(token))throw new Error(`V12.1 stabilization CSS missing ${token}`);
for(const token of ['.pv12-hero-visual','svg .hot','@media(max-width:760px)'])if(!art.includes(token))throw new Error(`V12.1 hero art CSS missing ${token}`);
const navBlock=js.match(/const nav=\[(.*?)\];\s*const navLinks/s)?.[1]||'';
const navCount=(navBlock.match(/\['/g)||[]).length;
if(navCount!==10)throw new Error(`Unified nav must contain exactly 10 destinations, found ${navCount}`);
for(const href of ['/','/predictions/','/horizons/','/causal/','/sports/','/intelligence/','/track-record/','/modules/','/sources/','/cameras/'])if(!navBlock.includes(`'${href}'`))throw new Error(`Unified nav missing ${href}`);
console.log(JSON.stringify({ok:true,pages:pages.length,nav_destinations:navCount,design_system:'providence-v12-1-unified-command-center'}));