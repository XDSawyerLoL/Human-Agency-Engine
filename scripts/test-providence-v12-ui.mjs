import fs from 'node:fs';

const pages=[
  ['home','public/index.html'],['sports','public/sports/index.html'],['matches','public/matches/index.html'],['track-record','public/track-record/index.html'],['backtest','public/backtest/index.html'],['sources','public/sources/index.html'],['alerts','public/alerts/index.html'],['settings','public/settings/index.html'],
  ['predictions','public/predictions/index.html'],['horizons','public/horizons/index.html'],['causal','public/causal/index.html'],['intelligence','public/intelligence/index.html'],['modules','public/modules/index.html'],['cameras','public/cameras/index.html']
];
for(const [name,file] of pages){const html=fs.readFileSync(file,'utf8');if(!html.includes('providence-atmosphere.js'))throw new Error(`${name}: missing Providence shell loader`);if(name!=='home'&&!html.includes(`data-page="${name}"`))throw new Error(`${name}: missing data-page theme`);}
const css=fs.readFileSync('public/providence-v12.css','utf8');
const fix=fs.readFileSync('public/providence-v12-1.css','utf8');
const art=fs.readFileSync('public/providence-v12-1-art.css','utf8');
const fidelity=fs.readFileSync('public/providence-v13-2-fixes.css','utf8');
const js=fs.readFileSync('public/providence-atmosphere.js','utf8');
for(const token of ['.pv12-sidebar','.pv12-scene','data-pv12-theme','fixture-card','graph-stage'])if(!css.includes(token))throw new Error(`V12 CSS missing ${token}`);
for(const token of ['Vue d’ensemble','Sports Calibration','Prochains matchs','Track Record','Historique & Backtest','Modèles & Données','Alertes & Suivi','Paramètres','Prédictions','Horizons','Causal World','Décision Intelligence','Modules','World Eye','pv12-hero-visual'])if(!js.includes(token))throw new Error(`Unified shell JS missing ${token}`);
for(const token of ['.v4-horizon-jump','position:relative!important','width:auto!important','.fixture-probs>div:nth-child(1)'])if(!fix.includes(token))throw new Error(`V12.1 stabilization CSS missing ${token}`);
for(const token of ['providence-v13-2-fixes.css','.pv12-hero-visual','svg .hot','@media(max-width:760px)'])if(!art.includes(token))throw new Error(`Hero/fidelity layer missing ${token}`);
for(const token of ['pv132-prediction-tabs','data-pv12-theme="horizons"','data-pv12-theme="modules"','data-pv12-theme="cameras"','.pv-team-badge img','causal-flow-row'])if(!fidelity.includes(token))throw new Error(`V13.2 fidelity CSS missing ${token}`);
const primary=js.match(/const primary=\[(.*?)\];\s*const advanced/s)?.[1]||'';
const advanced=js.match(/const advanced=\[(.*?)\];\s*const links/s)?.[1]||'';
const primaryCount=(primary.match(/\['/g)||[]).length,advancedCount=(advanced.match(/\['/g)||[]).length;
if(primaryCount!==8)throw new Error(`Primary nav must contain 8 destinations, found ${primaryCount}`);
if(advancedCount!==6)throw new Error(`Advanced nav must contain 6 destinations, found ${advancedCount}`);
for(const href of ['/','/sports/','/matches/','/track-record/','/backtest/','/sources/','/alerts/','/settings/'])if(!primary.includes(`'${href}'`))throw new Error(`Primary nav missing ${href}`);
for(const href of ['/predictions/','/horizons/','/causal/','/intelligence/','/modules/','/cameras/'])if(!advanced.includes(`'${href}'`))throw new Error(`Advanced nav missing ${href}`);
console.log(JSON.stringify({ok:true,pages:pages.length,primary:primaryCount,advanced:advancedCount,design_system:'providence-v13-2-reference-command-center'}));