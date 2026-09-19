(()=>{'use strict';

const page=(document.body.dataset.page||'home').trim();
const legacyVisualContract='quantic-unified.css?v=3.0';
const nativeV9Pages=new Set(['alerts','sports','track-record','sources','backtest','settings']);
const navPrimary=[
 ['home','/vision/','◉','Vision'],
 ['predictions','/predictions/','⌁','Prévisions'],
 ['analyst','/analyst/','△','Analyste'],
 ['alerts','/alerts/','♢','Alertes'],
 ['sports','/sports/','◈','Sports'],
 ['cameras','/cameras/','◎','World Eye'],
 ['track-record','/track-record/','✓','Calibration'],
 ['sources','/sources/','≋','Sources'],
 ['backtest','/backtest/','▤','Historique'],
 ['settings','/settings/','⚙','Réglages']
];

const loadCss=(href,match)=>{
  if(document.querySelector(`link[href*="${match}"]`))return;
  const link=document.createElement('link');
  link.rel='stylesheet';
  link.href=href;
  document.head.appendChild(link);
};

if(!nativeV9Pages.has(page)){
  loadCss('/providence-v15-fixes.css?v=clarity-1','providence-v15-fixes.css');
  loadCss('/providence-v16-platform.css?v=16.12','providence-v16-platform.css');
  loadCss('/providence-v16-rail.css?v=16.12','providence-v16-rail.css');
  loadCss('/providence-v16-ux.css?v=16.12','providence-v16-ux.css');
  loadCss('/providence-v16-mobile-fixes.css?v=16.12','providence-v16-mobile-fixes.css');
  loadCss('/providence-v16-product-cleanup.css?v=16.12','providence-v16-product-cleanup.css');
  if(page==='home')loadCss('/providence-timeline-v16-10.css?v=16.12','providence-timeline-v16-10.css');
  loadCss('/providence-v16-12-mobile.css?v=16.12','providence-v16-12-mobile.css');
}
loadCss('/quantic-system-v6.css?v=6.1','quantic-system-v6.css');
if(nativeV9Pages.has(page)){
  loadCss('/quantic-vision-v9.css?v=9.0','quantic-vision-v9.css');
}else if(document.body?.dataset?.visionNative!=='true'){
  const visionV7=document.querySelector('link[href*="quantic-vision-v7.css"]');
  if(visionV7)document.head.appendChild(visionV7);else loadCss('/quantic-vision-v7.css?v=7.0','quantic-vision-v7.css');
}
loadCss('/brand-2026.css?v=20260919','brand-2026.css');

document.body.classList.add('q-vision-shell');
document.body.dataset.product='quantic-vision';
if(document.title.startsWith('Providence'))document.title=document.title.replace(/^Providence\s*[—-]?\s*/,'Quantic Vision — ');

const productActive='vision';
const appLink=(key,href,label,icon)=>`<a href="${href}" class="${productActive===key?'active':''}" ${productActive===key?'aria-current="page"':''}><img class="q-nav-app-icon" src="/assets/brand-2026/${icon}" alt=""><span>${label}</span></a>`;
const global=document.createElement('header');
global.className='q-global-nav';
global.innerHTML=`
  <div class="q-global-nav-inner">
    <a class="q-global-brand" href="/" aria-label="Quantic Sillage — accueil">
      <img class="q-global-logo-mark" src="/assets/brand-2026/quantic-sillage-mark.svg?v=20260919.7" alt="">
      <span class="q-global-wordmark"><strong>Quantic</strong><strong>Sillage</strong></span>
    </a>
    <nav class="q-global-links" aria-label="Navigation Quantic">
      ${appLink('pulse','/pulse/','Pulse','pulse-mark.svg')}
      ${appLink('mail','/mail/','Mail','mail-mark.svg')}
      ${appLink('news','/news/','News','news-mark.svg')}
      ${appLink('vision','/vision/','Vision','vision-mark.svg')}
      <a href="/products/" class="q-hide-mobile"><span>Produits</span></a>
      <a href="/downloads/"><span>Outils</span></a>
      <a href="/quantic/" class="q-global-centre"><span class="q-global-status" aria-hidden="true"></span><span>Quantic ID</span></a>
    </nav>
  </div>`;
document.body.prepend(global);

const subnav=document.createElement('nav');
subnav.className='q-vision-subnav';
subnav.setAttribute('aria-label','Navigation Quantic Vision');
subnav.innerHTML=navPrimary.map(([key,href,icon,label],index)=>{
  const separator=index===4||index===6?'<span class="q-vision-subnav-sep" aria-hidden="true"></span>':'';
  const active=page===key;
  return `${separator}<a href="${href}" class="${active?'active':''}" ${active?'aria-current="page"':''}><i>${icon}</i><span>${label}</span></a>`;
}).join('');
global.insertAdjacentElement('afterend',subnav);

const main=document.querySelector('main');
if(main)main.classList.add('q-vision-content');

if(main&&page==='predictions'&&!main.querySelector('.p16-time-rail')){
  const rail=document.createElement('nav');
  rail.className='p16-time-rail';
  rail.setAttribute('aria-label','Navigation temporelle');
  rail.innerHTML=`
    <a class="p16-now active" href="/predictions/"><i></i><span><b>PRÉSENT</b><small>état observé</small></span></a>
    <a class="p16-time-node" style="--c:#ffc74d" href="/predictions/?horizon=immediate"><b>≤ 72 H</b><small>immédiat</small></a>
    <a class="p16-time-node" style="--c:#ff9f43" href="/predictions/?horizon=near"><b>≤ 1 MOIS</b><small>court terme</small></a>
    <a class="p16-time-node" style="--c:#9b5cff" href="/predictions/?horizon=medium"><b>≤ 3 MOIS</b><small>moyen terme</small></a>
    <a class="p16-time-node" style="--c:#148cff" href="/predictions/?horizon=long"><b>≤ 1 AN</b><small>long terme</small></a>
    <a class="p16-time-node" style="--c:#20d8ff" href="/predictions/?horizon=deep"><b>&gt; 1 AN</b><small>stratégique</small></a>`;
  main.prepend(rail);
}

if(main&&!document.querySelector('.q-unified-footer')){
  const footer=document.createElement('footer');
  footer.className='q-unified-footer';
  footer.innerHTML='<span class="q-unified-footer-brand"><img src="/assets/brand-2026/quantic-sillage-mark.svg?v=20260919.7" alt="">Quantic Sillage · QUANTIC VISION</span><span><a href="/track-record/">Méthode & transparence</a> · <a href="/downloads/">Outils</a> · <a href="/products/">Écosystème Quantic</a></span>';
  main.insertAdjacentElement('afterend',footer);
}

if(page==='home'&&document.body?.dataset?.visionNative!=='true'&&!document.querySelector('script[src*="providence-timeline-v16-10.js"]')){
  const script=document.createElement('script');
  script.src='/providence-timeline-v16-10.js?v=16.12';
  script.async=true;
  document.body.appendChild(script);
}
})();