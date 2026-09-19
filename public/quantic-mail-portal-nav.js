(()=>{'use strict';
const NAV_ID='quantic-mail-global-nav';
const THEME_ID='quantic-system-v6';
const MAIL_THEME_ID='quantic-mail-v7';
const BRAND_THEME_ID='quantic-brand-2026';
function ensureTheme(){
  if(!document.head)return;
  if(!document.getElementById(THEME_ID)){
    const link=document.createElement('link');link.id=THEME_ID;link.rel='stylesheet';link.href='/quantic-system-v6.css?v=6.0';document.head.appendChild(link);
  }
  if(!document.getElementById(BRAND_THEME_ID)){
    const link=document.createElement('link');link.id=BRAND_THEME_ID;link.rel='stylesheet';link.href='/brand-2026.css?v=20260919.2';document.head.appendChild(link);
  }
  if(!document.getElementById(MAIL_THEME_ID)){
    const link=document.createElement('link');link.id=MAIL_THEME_ID;link.rel='stylesheet';link.href='/quantic-mail-v7.css?v=7.0';document.head.appendChild(link);
  }
}
function navMarkup(){return '<a class="qn-global-brand" href="/" aria-label="Quantic Sillage accueil"><img class="qn-global-logo" src="/assets/brand-2026/quantic-sillage-mark.svg" alt=""><span class="qn-global-wordmark">Quantic Sillage</span></a><nav class="qn-global-links" aria-label="Navigation principale"><a href="/vision/"><img class="q-nav-app-icon" src="/assets/brand-2026/vision-mark.svg" alt=""><span>Vision</span></a><a class="active" href="/mail/" aria-current="page"><img class="q-nav-app-icon" src="/assets/brand-2026/mail-mark.svg" alt=""><span>Mail</span></a><a href="/pulse/"><img class="q-nav-app-icon" src="/assets/brand-2026/pulse-mark.svg" alt=""><span>Pulse</span></a><a href="/news/"><img class="q-nav-app-icon" src="/assets/brand-2026/news-mark.svg" alt=""><span>News</span></a><a href="/products/"><span>Produits</span></a><a href="/downloads/"><span>Outils</span></a><a class="centre" href="/quantic/">Quantic ID</a></nav>'}
function ensureNav(){
  ensureTheme();
  if(!document.body)return;
  let header=document.getElementById(NAV_ID)||document.querySelector('.qn-global-nav');
  if(!header){
    header=document.createElement('header');
    document.body.prepend(header);
  }
  header.id=NAV_ID;
  header.className='qn-global-nav';
  header.setAttribute('aria-label','Navigation Quantic');
  header.innerHTML=navMarkup();
}
function settle(){
  ensureTheme();
  ensureNav();
  setTimeout(ensureNav,250);
  setTimeout(ensureNav,900);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',settle,{once:true});else settle();
window.addEventListener('load',ensureNav,{once:true});
})();