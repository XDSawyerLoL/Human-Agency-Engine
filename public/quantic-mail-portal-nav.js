(()=>{'use strict';
const NAV_ID='quantic-mail-global-nav';
const THEME_ID='quantic-system-v6';
function ensureTheme(){if(document.getElementById(THEME_ID)||!document.head)return;const link=document.createElement('link');link.id=THEME_ID;link.rel='stylesheet';link.href='/quantic-system-v6.css?v=6.0';document.head.appendChild(link);}
function ensureNav(){
  ensureTheme();
  if(document.getElementById(NAV_ID)||document.querySelector('.qn-global-nav')||!document.body)return;
  const header=document.createElement('header');
  header.id=NAV_ID;
  header.className='qn-global-nav';
  header.setAttribute('aria-label','Navigation Quantic');
  header.innerHTML='<a class="qn-global-brand" href="/" aria-label="Quantic accueil"><span class="qn-global-mark" aria-hidden="true"></span><span>QUANTIC</span></a><nav class="qn-global-links" aria-label="Navigation principale"><a href="/vision/">Vision</a><a class="active" href="/mail/" aria-current="page">Mail</a><a href="/pulse/">Pulse</a><a href="/network/">Network</a><a href="/products/">Produits</a><a href="/downloads/">Téléchargements</a><a class="centre" href="/quantic/">Quantic ID</a></nav>';
  document.body.prepend(header);
}
function settle(){
  ensureTheme();
  ensureNav();
  setTimeout(ensureNav,250);
  setTimeout(ensureNav,900);
}
if(document.readyState==='complete')settle();
else window.addEventListener('load',settle,{once:true});
})();