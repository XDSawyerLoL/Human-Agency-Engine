import fs from 'node:fs';
const read=p=>fs.readFileSync(p,'utf8');
const primary=[
 ['home','public/index.html'],['sports','public/sports/index.html'],['matches','public/matches/index.html'],['track-record','public/track-record/index.html'],['backtest','public/backtest/index.html'],['sources','public/sources/index.html'],['alerts','public/alerts/index.html'],['settings','public/settings/index.html']
];
const legacy=['app.css','world-eye-v4.css','providence-v11.css','providence-v12.css','providence-v13.css','providence-atmosphere.js'];
for(const [name,file] of primary){const html=read(file);if(!html.includes('providence-v14.css'))throw new Error(`${name}: V14 stylesheet missing`);if(!html.includes('providence-v14-shell.js'))throw new Error(`${name}: V14 shell missing`);if(!html.includes(`data-page="${name}"`))throw new Error(`${name}: data-page missing`);for(const token of legacy)if(html.includes(token))throw new Error(`${name}: legacy visual dependency still loaded: ${token}`);}
const css=read('public/providence-v14.css'),components=read('public/providence-v14-components.css'),overviewCss=read('public/providence-v14-overview.css'),shell=read('public/providence-v14-shell.js'),overview=read('public/overview-v14.js'),sports=read('public/sports/sports.js');
for(const token of ['.pv14-sidebar','.pv14-profile','.pv14-hero','.v4-metric-strip','.fixture-grid','.pv-match-layout','.pv-settings-grid','.pv-alert-layout'])if(!css.includes(token))throw new Error(`V14 CSS missing ${token}`);
for(const token of ['fixture-why-grid','pv-alert-row','v8-bucket','pv-quality-item','.pv-toggle.on'])if(!components.includes(token))throw new Error(`V14 dynamic component CSS missing ${token}`);
for(const token of ['pv14-overview-grid','pv14-priority-row','pv14-domains','pv14-trend-bars'])if(!overviewCss.includes(token))throw new Error(`V14 overview CSS missing ${token}`);
for(const label of ['Vue d’ensemble','Sports Calibration','Prochains matchs','Track Record','Historique & Backtest','Modèles & Données','Alertes & Suivi','Paramètres'])if(!shell.includes(label))throw new Error(`V14 shell nav missing ${label}`);
for(const token of ['/api/snapshot','/api/track-record','overviewPriorities','overviewDomains','overviewDecision','overviewAlerts'])if(!overview.includes(token))throw new Error(`V14 overview renderer missing ${token}`);
for(const token of ['France','Ligue 1','slice(0,4)','Pourquoi Providence donne ce résultat','ELO DOMICILE','fixtureProvider'])if(!sports.includes(token))throw new Error(`V14 Sports behavior missing ${token}`);
for(const file of ['public/sports/index.html','public/matches/index.html'])if(!read(file).includes('team-crests-v13.js'))throw new Error(`${file}: real crest hydration missing`);
if(css.includes('@import'))throw new Error('V14 base CSS must not import legacy stacks');
console.log(JSON.stringify({ok:true,version:'v14',primary_pages:primary.length,legacy_visual_dependencies:'removed',sports_preview:4,design:'approved-reference-cockpit'}));