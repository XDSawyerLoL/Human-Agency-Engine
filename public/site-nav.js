/* Navigation commune Quantic Sillage — 2026-10-13. N'affecte pas les sous-navigations d'applications. */
(()=>{'use strict';
if(document.documentElement.dataset.quanticSiteNav==='1')return;
document.documentElement.dataset.quanticSiteNav='1';
const links=[
  {label:'Services',href:'/services/'},
  {label:'Offres & tarifs',href:'/plans/'},
  {label:"L’entreprise",href:'/entreprise/'}
];
const families=[
 {title:'Identité & sécurité',items:[['Quantic ID','/quantic/','identity-vault-mark.svg'],['Quantic Network','/downloads/#network','quantic-sillage-mark.svg']]},
 {title:'Navigation & système',items:[['GEKKO','/gekko/','gekko-mark.svg?v=20261013.2'],['Quantic OS','/downloads/#quantic-os','os-mark.svg']]},
 {title:'Communication & création',items:[['Quantic Mail','/mail/','mail-mark.svg'],['ZOON','/pulse/','zoon-mark.svg'],['Quantic Studio','/downloads/#quantic-studio','studio-mark.svg']]},
 {title:'Analyse & information',items:[['Quantic Vision','/vision/','vision-mark.svg'],['Quantic News','/news/','news-mark.svg']]}
];
function active(href){const p=location.pathname.replace(/\/+$/,'')+'/';return p===href||href==='/ecosystem/'&&p==='/downloads/'}
function productsMarkup(){return families.map(f=>'<section class="qs-nav-family"><h3>'+f.title+'</h3>'+f.items.map(([label,href,icon])=>'<a href="'+href+'"><img loading="lazy" src="/assets/brand-2026/'+icon+'" alt="" aria-hidden="true">'+label+'</a>').join('')+'</section>').join('')}
function link(obj){return '<a href="'+obj.href+'"'+(active(obj.href)?' aria-current="page"':'')+'>'+obj.label+'</a>'}
function init(){
 if(document.querySelector('.qs-site-header'))return;
 const header=document.createElement('header');header.className='qs-site-header';
 header.innerHTML=`
 <div class="qs-site-head-inner">
   <a class="qs-site-brand" href="/" aria-label="Quantic Sillage — Accueil">
     <img src="/assets/brand-2026/quantic-sillage-mark.svg?v=20260919.9" width="38" height="38" alt="">
     <span>Quantic<strong>Sillage</strong></span>
   </a>
   <nav class="qs-site-desktop" aria-label="Navigation du site">
     ${link(links[0])}
     <details class="qs-site-products">
       <summary>Produits <span class="qs-chevron" aria-hidden="true">⌄</span></summary>
       <div class="qs-site-products-panel">
         <div class="qs-site-products-header"><strong>L'écosystème Quantic</strong><a href="/ecosystem/">Voir tous les produits <span aria-hidden="true">→</span></a></div>
         <div class="qs-site-products-grid">${productsMarkup()}</div>
         <div class="qs-site-products-foot"><a href="/downloads/">Téléchargements & versions</a></div>
       </div>
     </details>
     ${link(links[1])}
     ${link(links[2])}
   </nav>
   <div class="qs-site-actions"><a class="qs-site-id" href="/quantic/">Quantic ID</a><a class="qs-site-contact" href="/contact/">Parler d'un projet <span aria-hidden="true">↗</span></a></div>
   <button class="qs-site-menu-toggle" type="button" aria-controls="qs-site-mobile-panel" aria-expanded="false" aria-label="Ouvrir le menu"><span></span><span></span><span></span></button>
 </div>
 <nav id="qs-site-mobile-panel" class="qs-site-mobile-panel" aria-label="Navigation mobile" hidden>
   ${link(links[0])}
   <details><summary>Produits <span aria-hidden="true">⌄</span></summary>
     <div class="qs-site-mobile-products"><a href="/ecosystem/">Tous les produits →</a>${productsMarkup()}<a href="/downloads/">Téléchargements & versions</a></div>
   </details>
   ${link(links[1])}
   ${link(links[2])}
   <a href="/quantic/">Quantic ID</a>
   <a class="qs-site-mobile-contact" href="/contact/">Parler d'un projet ↗</a>
 </nav>`;
 document.body.prepend(header);
 document.documentElement.classList.add('qs-site-nav-enabled');
 const toggle=header.querySelector('.qs-site-menu-toggle');
 const panel=header.querySelector('#qs-site-mobile-panel');
 const dropdown=header.querySelector('.qs-site-products');
 function closeMobile(){panel.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-label','Ouvrir le menu');toggle.classList.remove('is-open')}
 toggle.addEventListener('click',()=>{const open=panel.hidden;panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'Fermer le menu':'Ouvrir le menu');toggle.classList.toggle('is-open',open);if(open&&dropdown)dropdown.open=false});
 panel.addEventListener('click',event=>{if(event.target.closest('a'))closeMobile()});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeMobile();if(dropdown?.open){dropdown.open=false;dropdown.querySelector('summary')?.focus()}}});
 document.addEventListener('click',event=>{if(dropdown?.open&&!dropdown.contains(event.target))dropdown.open=false});
 window.addEventListener('resize',()=>{if(innerWidth>1024&&!panel.hidden)closeMobile()});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
