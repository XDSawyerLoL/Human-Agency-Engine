(()=>{'use strict';
const page=(document.body.dataset.page||'home').trim();
const navPrimary=[
 ['home','/','◉','Vue d’ensemble'],
 ['predictions','/predictions/','⌁','Prédictions'],
 ['horizons','/horizons/','⌛','Horizons'],
 ['causal','/causal/','⌘','Causes & Preuves'],
 ['track-record','/track-record/','◎','Calibration'],
 ['alerts','/alerts/','♢','Alertes & Veille'],
 ['sources','/sources/','≋','Signaux & Données']
];
const navIntel=[
 ['intelligence','/intelligence/','◇','Scénarios & Décision'],
 ['sports','/sports/','◈','Sports Intelligence'],
 ['cameras','/cameras/','◉','World Eye']
];
const navSystem=[
 ['backtest','/backtest/','▤','Backtest Lab'],
 ['modules','/modules/','▦','Modules & IA'],
 ['settings','/settings/','⚙','Paramètres']
];
const iconize=s=>s;
const links=rows=>rows.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><i>${iconize(icon)}</i><span>${label}</span></a>`).join('');
const allLinks=()=>`${links(navPrimary)}<div class="p15-nav-sep"></div><div class="p15-nav-label">Intelligence</div>${links(navIntel)}<div class="p15-nav-label">Système</div>${links(navSystem)}`;
if(!document.querySelector('link[href*="providence-v15-fixes.css"]')){const l=document.createElement('link');l.rel='stylesheet';l.href='/providence-v15-fixes.css?v=15';document.head.appendChild(l)}
if(!document.querySelector('.p15-sidebar')){
 const side=document.createElement('aside');
 side.className='p15-sidebar';
 side.innerHTML=`
 <a class="p15-brand" href="/"><span class="p15-logo" aria-hidden="true"></span><span><b>PROVIDENCE</b><span>PREDICTIVE INTELLIGENCE</span></span></a>
 <nav class="p15-nav" aria-label="Navigation Providence">${links(navPrimary)}</nav>
 <div class="p15-nav-sep"></div><div class="p15-nav-label">Intelligence</div><nav class="p15-nav">${links(navIntel)}</nav>
 <div class="p15-nav-label">Système</div><nav class="p15-nav">${links(navSystem)}</nav>
 <div class="p15-sidebar-spacer"></div>
 <div class="p15-mission"><strong>Notre mission</strong>Transformer les signaux mondiaux en prédictions probabilistes fiables pour des décisions plus justes.<b>Voir avant. Décider mieux.</b></div>
 <div class="p15-usercard"><span class="avatar">△</span><span><b>Analyste Providence</b><small>◆ Niveau Élite</small></span></div>
 <div class="p15-system"><span>●</span> Système en ligne</div>`;
 document.body.prepend(side);
}
const main=document.querySelector('main');if(main)main.classList.add('p15-main');
if(main&&!main.querySelector('.p15-topbar')){
 const top=document.createElement('div');top.className='p15-topbar';top.innerHTML=`<div class="p15-search">⌕ Rechercher un signal, un scénario, une entité…</div><div class="p15-iconbtn">☼</div><div class="p15-iconbtn">♢</div><div class="p15-analyst"><span class="ring">△</span><span><b>Analyste Providence</b><small>◆ Niveau Élite</small></span></div>`;main.prepend(top);
}
if(!document.querySelector('.p15-mobilebar')){
 const bar=document.createElement('div');bar.className='p15-mobilebar';bar.innerHTML='<a class="p15-mobilebrand" href="/"><i></i><span>PROVIDENCE</span></a><button class="p15-mobile-toggle" type="button" aria-label="Ouvrir le menu" aria-expanded="false">☰</button>';
 const overlay=document.createElement('button');overlay.className='p15-mobile-overlay';overlay.type='button';overlay.setAttribute('aria-label','Fermer le menu');
 const drawer=document.createElement('aside');drawer.className='p15-mobile-drawer';drawer.innerHTML=`<nav class="p15-nav" aria-label="Navigation mobile Providence">${allLinks()}</nav>`;
 document.body.append(bar,overlay,drawer);
 const toggle=bar.querySelector('.p15-mobile-toggle');const setOpen=open=>{document.body.classList.toggle('p15-menu-open',open);toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'×':'☰'};
 toggle.addEventListener('click',()=>setOpen(!document.body.classList.contains('p15-menu-open')));overlay.addEventListener('click',()=>setOpen(false));drawer.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>setOpen(false)));document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false)});
}
})();