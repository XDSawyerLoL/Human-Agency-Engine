import fs from 'node:fs';

const pages=[
  ['home','public/index.html'],['predictions','public/predictions/index.html'],['horizons','public/horizons/index.html'],['causal','public/causal/index.html'],['sports','public/sports/index.html'],['intelligence','public/intelligence/index.html'],['track-record','public/track-record/index.html'],['modules','public/modules/index.html'],['sources','public/sources/index.html'],['cameras','public/cameras/index.html']
];
for(const [name,file] of pages){
  const html=fs.readFileSync(file,'utf8');
  if(!html.includes('providence-atmosphere.js'))throw new Error(`${name}: missing Providence V12 shell loader`);
  if(name!=='home'&&!html.includes(`data-page="${name}"`))throw new Error(`${name}: missing data-page theme`);
}
const css=fs.readFileSync('public/providence-v12.css','utf8');
const js=fs.readFileSync('public/providence-atmosphere.js','utf8');
for(const token of ['.pv12-sidebar','.pv12-scene','data-pv12-theme','fixture-card','graph-stage'])if(!css.includes(token))throw new Error(`V12 CSS missing ${token}`);
for(const token of ['providence-v12.css','pv12-sidebar','Sports Calibration','Monde en direct'])if(!js.includes(token))throw new Error(`V12 shell JS missing ${token}`);
console.log(JSON.stringify({ok:true,pages:pages.length,design_system:'providence-v12-command-center'}));