(()=>{'use strict';
const page=(document.body.dataset.page||'home').trim();
const primary=[
 ['home','/','◉','Vue d’ensemble'],['sports','/sports/','◈','Sports Calibration'],['matches','/matches/','◷','Prochains matchs'],['track-record','/track-record/','▥','Track Record'],['backtest','/backtest/','▤','Historique & Backtest'],['sources','/sources/','≋','Modèles & Données'],['alerts','/alerts/','♢','Alertes & Suivi'],['settings','/settings/','⚙','Paramètres']
];
const advanced=[
 ['predictions','/predictions/','⌁','Prédictions'],['horizons','/horizons/','⌛','Horizons'],['causal','/causal/','⌘','Causal World'],['intelligence','/intelligence/','◇','Décision Intelligence'],['modules','/modules/','▦','Modules'],['cameras','/cameras/','◉','Monde en direct']
];
const links=rows=>rows.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><span class="icon">${icon}</span><span>${label}</span></a>`).join('');
if(!document.querySelector('.pv14-sidebar')){
 const activeAdvanced=advanced.some(([k])=>k===page);
 const a=document.createElement('aside');a.className='pv14-sidebar';a.innerHTML=`<a class="pv14-brand" href="/"><span class="pv14-mark" aria-hidden="true"></span><span><strong>PROVIDENCE</strong><small>VOIR · CALIBRER · GAGNER.</small></span></a><nav class="pv14-nav" aria-label="Navigation Providence">${links(primary)}</nav><div class="pv14-advanced ${activeAdvanced?'open':''}"><button type="button" class="pv14-advanced-toggle" aria-expanded="${activeAdvanced?'true':'false'}"><span>ANALYSES AVANCÉES</span><b>${activeAdvanced?'−':'+'}</b></button><nav class="pv14-advanced-nav" aria-label="Analyses avancées">${links(advanced)}</nav></div><div class="pv14-sidebar-spacer"></div><div class="pv14-orb" aria-hidden="true"></div><div class="pv14-mission"><strong>Notre mission</strong><b>Mesurer la réalité.</b><br>Améliorer la prédiction.<br>Battre l’incertitude.</div><div class="pv14-sidefoot">© 2026 Providence AI<br>Tous droits réservés.<div class="pv14-status"><i></i>Système opérationnel</div></div>`;document.body.prepend(a);
 const t=a.querySelector('.pv14-advanced-toggle');t?.addEventListener('click',()=>{const box=a.querySelector('.pv14-advanced');const open=box.classList.toggle('open');t.setAttribute('aria-expanded',String(open));t.querySelector('b').textContent=open?'−':'+'});
}
if(!document.querySelector('.pv14-profile')){const p=document.createElement('div');p.className='pv14-profile';p.innerHTML='<span class="tiny">☼</span><span class="tiny">♢<sup style="color:#38adff;font-size:.55rem">8</sup></span><span><strong>Analyste Providence</strong><small><b>◆</b> Niveau Live</small></span><span class="badge">△</span>';document.body.appendChild(p)}
const main=document.querySelector('main');if(main)main.classList.add('pv14-main');
const hero=document.querySelector('.pv14-hero,.sports-hero,.pv-product-hero,.v5-hero,.v4-page-hero,.causal-hero');
if(hero&&!hero.querySelector('.pv14-art')){const art=document.createElement('div');art.className='pv14-art';art.setAttribute('aria-hidden','true');art.innerHTML='<span class="globe"></span><span class="reticle"></span><span class="satellite"></span><span class="scan"></span>';hero.prepend(art)}
})();