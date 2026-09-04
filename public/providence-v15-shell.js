(()=>{'use strict';
const page=(document.body.dataset.page||'home').trim();
const navPrimary=[
 ['home','/','◉','Accueil'],
 ['predictions','/predictions/','⌁','Prédictions'],
 ['analyst','/analyst/','△','Providence Analyst'],
 ['alerts','/alerts/','♢','Alertes & Veille']
];
const navExplore=[
 ['sports','/sports/','◈','Sports Intelligence'],
 ['cameras','/cameras/','◉','World Eye']
];
const navTransparency=[
 ['track-record','/track-record/','◎','Calibration'],
 ['sources','/sources/','≋','Sources & données'],
 ['backtest','/backtest/','▤','Historique & backtest']
];
const navTools=[
 ['settings','/settings/','⚙','Paramètres']
];
const allRows=[...navPrimary,...navExplore,...navTransparency,...navTools];
const pageLabel=(allRows.find(([k])=>k===page)||['','','','Console Providence'])[3];
const links=rows=>rows.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><i>${icon}</i><span>${label}</span></a>`).join('');
const details=(label,rows)=>`<details class="p15-nav-more" ${rows.some(([k])=>k===page)?'open':''}><summary>${label}</summary><nav class="p15-nav">${links(rows)}</nav></details>`;
const allLinks=()=>`<nav class="p15-nav">${links(navPrimary)}</nav>${details('Explorer',navExplore)}${details('Méthode & transparence',navTransparency)}${details('Outils',navTools)}`;
const loadCss=(href,match)=>{if(!document.querySelector(`link[href*="${match}"]`)){const l=document.createElement('link');l.rel='stylesheet';l.href=href;document.head.appendChild(l)}};
loadCss('/providence-v15-fixes.css?v=clarity-1','providence-v15-fixes.css');
loadCss('/providence-v16-platform.css?v=16.9','providence-v16-platform.css');
loadCss('/providence-v16-rail.css?v=16.9','providence-v16-rail.css');
loadCss('/providence-v16-ux.css?v=16.9','providence-v16-ux.css');
loadCss('/providence-v16-mobile-fixes.css?v=16.9','providence-v16-mobile-fixes.css');
loadCss('/providence-v16-product-cleanup.css?v=16.9','providence-v16-product-cleanup.css');
if(page==='home')loadCss('/providence-timeline-interactive.css?v=16.9','providence-timeline-interactive.css');
if(!document.querySelector('.p15-sidebar')){
 const side=document.createElement('aside');
 side.className='p15-sidebar';
 side.innerHTML=`
 <a class="p15-brand" href="/"><span class="p15-logo" aria-hidden="true"></span><span><b>PROVIDENCE</b><span>PREDICTIVE INTELLIGENCE</span></span></a>
 <nav class="p15-nav" aria-label="Navigation Providence">${links(navPrimary)}</nav>
 ${details('Explorer',navExplore)}
 ${details('Méthode & transparence',navTransparency)}
 ${details('Outils',navTools)}
 <div class="p15-sidebar-spacer"></div>
 <div class="p15-mission"><strong>Mission</strong>Transformer des signaux vérifiables en prévisions utiles.<b>Voir avant. Décider mieux.</b></div>
 <a class="p15-usercard" href="/analyst/"><span class="avatar">△</span><span><b>Analyste Providence</b><small>Dialogue avec le moteur</small></span></a>
 <div class="p15-system"><span>●</span> Système en ligne</div>`;
 document.body.prepend(side);
}
const main=document.querySelector('main');if(main)main.classList.add('p15-main');
if(main&&!main.querySelector('.p15-topbar')){
 const top=document.createElement('div');top.className='p15-topbar';top.innerHTML=`<div class="p16-platform-head"><i></i><span><small>PROVIDENCE / TEMPORAL INTELLIGENCE</small><b>${pageLabel}<em>· live</em></b></span></div><a class="p15-analyst" href="/analyst/" aria-label="Interroger Providence"><span class="ring">△</span><span><b>Analyste Providence</b><small>Interroger le moteur</small></span></a>`;main.prepend(top);
}
if(main&&page==='predictions'&&!main.querySelector('.p16-time-rail')){
 const rail=document.createElement('nav');rail.className='p16-time-rail';rail.setAttribute('aria-label','Navigation temporelle');rail.innerHTML=`
  <a class="p16-now active" href="/predictions/"><i></i><span><b>PRÉSENT</b><small>état observé</small></span></a>
  <a class="p16-time-node" style="--c:#ffc85a" href="/predictions/?horizon=immediate"><b>≤ 72 H</b><small>immédiat</small></a>
  <a class="p16-time-node" style="--c:#e9a85d" href="/predictions/?horizon=near"><b>≤ 1 MOIS</b><small>court terme</small></a>
  <a class="p16-time-node" style="--c:#a777ff" href="/predictions/?horizon=medium"><b>≤ 3 MOIS</b><small>moyen terme</small></a>
  <a class="p16-time-node" style="--c:#4f8dff" href="/predictions/?horizon=long"><b>≤ 1 AN</b><small>long terme</small></a>
  <a class="p16-time-node" style="--c:#57d8ff" href="/predictions/?horizon=deep"><b>&gt; 1 AN</b><small>stratégique</small></a>`;
 const top=main.querySelector('.p15-topbar');top?.insertAdjacentElement('afterend',rail);
}
if(!document.querySelector('.p15-mobilebar')){
 const bar=document.createElement('div');bar.className='p15-mobilebar';bar.innerHTML='<a class="p15-mobilebrand" href="/"><i></i><span>PROVIDENCE</span></a><button class="p15-mobile-toggle" type="button" aria-label="Ouvrir le menu" aria-expanded="false">☰</button>';
 const overlay=document.createElement('button');overlay.className='p15-mobile-overlay';overlay.type='button';overlay.setAttribute('aria-label','Fermer le menu');
 const drawer=document.createElement('aside');drawer.className='p15-mobile-drawer';drawer.innerHTML=`<div aria-label="Navigation mobile Providence">${allLinks()}</div>`;
 document.body.append(bar,overlay,drawer);
 const toggle=bar.querySelector('.p15-mobile-toggle');const setOpen=open=>{document.body.classList.toggle('p15-menu-open',open);toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'×':'☰'};
 toggle.addEventListener('click',()=>setOpen(!document.body.classList.contains('p15-menu-open')));overlay.addEventListener('click',()=>setOpen(false));drawer.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>setOpen(false)));document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false)});
}
if(!document.querySelector('.p16-mobile-dock')){
 const dock=document.createElement('nav');dock.className='p16-mobile-dock';dock.setAttribute('aria-label','Navigation principale mobile');
 const items=[['home','/','◉','Accueil'],['predictions','/predictions/','⌁','Prévisions'],['analyst','/analyst/','△','Analyste'],['alerts','/alerts/','♢','Alertes']];
 dock.innerHTML=items.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><i>${icon}</i><span>${label}</span></a>`).join('');
 document.body.appendChild(dock);
}
if(page==='home'&&!document.querySelector('script[src*="providence-timeline-interactive.js"]')){
 const s=document.createElement('script');s.src='/providence-timeline-interactive.js?v=16.9';s.async=true;document.body.appendChild(s);
}
})();