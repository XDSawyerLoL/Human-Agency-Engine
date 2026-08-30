(()=>{'use strict';
const page=(document.body.dataset.page||'home').trim();
const navPrimary=[
 ['home','/','◉','Vue d’ensemble'],
 ['predictions','/predictions/','⌁','Prédictions'],
 ['horizons','/horizons/','⌛','Horizons'],
 ['analyst','/analyst/','△','Providence Analyst'],
 ['track-record','/track-record/','◎','Calibration'],
 ['alerts','/alerts/','♢','Alertes & Veille']
];
const navExplore=[
 ['causal','/causal/','⌘','Causes & Preuves'],
 ['sources','/sources/','≋','Signaux & Données'],
 ['intelligence','/intelligence/','◇','Scénarios & Décision'],
 ['sports','/sports/','◈','Sports Intelligence'],
 ['cameras','/cameras/','◉','World Eye']
];
const navTools=[
 ['backtest','/backtest/','▤','Backtest Lab'],
 ['modules','/modules/','▦','Modules & IA'],
 ['settings','/settings/','⚙','Paramètres']
];
const links=rows=>rows.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><i>${icon}</i><span>${label}</span></a>`).join('');
const details=(label,rows)=>`<details class="p15-nav-more" ${rows.some(([k])=>k===page)?'open':''}><summary>${label}</summary><nav class="p15-nav">${links(rows)}</nav></details>`;
const allLinks=()=>`<nav class="p15-nav">${links(navPrimary)}</nav>${details('Explorer',navExplore)}${details('Outils',navTools)}`;
if(!document.querySelector('link[href*="providence-v15-fixes.css"]')){const l=document.createElement('link');l.rel='stylesheet';l.href='/providence-v15-fixes.css?v=clarity-1';document.head.appendChild(l)}
if(!document.querySelector('.p15-sidebar')){
 const side=document.createElement('aside');
 side.className='p15-sidebar';
 side.innerHTML=`
 <a class="p15-brand" href="/"><span class="p15-logo" aria-hidden="true"></span><span><b>PROVIDENCE</b><span>PREDICTIVE INTELLIGENCE</span></span></a>
 <nav class="p15-nav" aria-label="Navigation Providence">${links(navPrimary)}</nav>
 ${details('Explorer',navExplore)}
 ${details('Outils',navTools)}
 <div class="p15-sidebar-spacer"></div>
 <div class="p15-mission"><strong>Mission</strong>Transformer des signaux vérifiables en prévisions utiles.<b>Voir avant. Décider mieux.</b></div>
 <a class="p15-usercard" href="/analyst/"><span class="avatar">△</span><span><b>Analyste Providence</b><small>Dialogue avec le moteur</small></span></a>
 <div class="p15-system"><span>●</span> Système en ligne</div>`;
 document.body.prepend(side);
}
const main=document.querySelector('main');if(main)main.classList.add('p15-main');
if(main&&!main.querySelector('.p15-topbar')){
 const top=document.createElement('div');top.className='p15-topbar';top.innerHTML=`<span class="p15-topbar-context">Voir avant. Décider mieux.</span><a class="p15-analyst" href="/analyst/"><span class="ring">△</span><span><b>Analyste Providence</b><small>Interroger le moteur</small></span></a>`;main.prepend(top);
}
if(!document.querySelector('.p15-mobilebar')){
 const bar=document.createElement('div');bar.className='p15-mobilebar';bar.innerHTML='<a class="p15-mobilebrand" href="/"><i></i><span>PROVIDENCE</span></a><button class="p15-mobile-toggle" type="button" aria-label="Ouvrir le menu" aria-expanded="false">☰</button>';
 const overlay=document.createElement('button');overlay.className='p15-mobile-overlay';overlay.type='button';overlay.setAttribute('aria-label','Fermer le menu');
 const drawer=document.createElement('aside');drawer.className='p15-mobile-drawer';drawer.innerHTML=`<div aria-label="Navigation mobile Providence">${allLinks()}</div>`;
 document.body.append(bar,overlay,drawer);
 const toggle=bar.querySelector('.p15-mobile-toggle');const setOpen=open=>{document.body.classList.toggle('p15-menu-open',open);toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'×':'☰'};
 toggle.addEventListener('click',()=>setOpen(!document.body.classList.contains('p15-menu-open')));overlay.addEventListener('click',()=>setOpen(false));drawer.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>setOpen(false)));document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false)});
}
})();