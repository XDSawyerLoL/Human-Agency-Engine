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
 ['sports','/sports/','◈','Sports Intelligence']
];
const navSystem=[
 ['backtest','/backtest/','▤','Backtest Lab'],
 ['modules','/modules/','▦','Modules & IA'],
 ['settings','/settings/','⚙','Paramètres']
];
const iconize=s=>s;
const links=rows=>rows.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><i>${iconize(icon)}</i><span>${label}</span></a>`).join('');
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
})();