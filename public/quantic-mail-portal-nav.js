(()=>{'use strict';
const NAV_ID='quantic-mail-global-nav';
const THEME_ID='quantic-system-v6';
const MAIL_THEME_ID='quantic-mail-v7';
function ensureTheme(){
  if(!document.head)return;
  if(!document.getElementById(THEME_ID)){
    const link=document.createElement('link');link.id=THEME_ID;link.rel='stylesheet';link.href='/quantic-system-v6.css?v=6.0';document.head.appendChild(link);
  }
  if(!document.getElementById(MAIL_THEME_ID)){
    const link=document.createElement('link');link.id=MAIL_THEME_ID;link.rel='stylesheet';link.href='/quantic-mail-v7.css?v=7.0';document.head.appendChild(link);
  }
}
function navMarkup(){return '<a class="qn-global-brand" href="/" aria-label="Quantic Sillage accueil"><span class="qn-global-mark" aria-hidden="true"></span><span>QUANTIC SILLAGE</span></a><nav class="qn-global-links" aria-label="Navigation principale"><a href="/vision/">Vision</a><a class="active" href="/mail/" aria-current="page">Mail</a><a href="/pulse/">Pulse</a><a href="/news/">News</a><a href="/network/">Network</a><a href="/products/">Produits</a><a href="/downloads/">Téléchargements</a><a class="centre" href="/quantic/">Quantic ID</a></nav>'}
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