(()=>{'use strict';
const page=(document.body.dataset.page||'home').trim();
const core=[
 ['home','/','◉','Vue d’ensemble'],
 ['predictions','/predictions/','⌁','Prédictions'],
 ['horizons','/horizons/','⌛','Horizons'],
 ['causal','/causal/','⌘','Causal World'],
 ['intelligence','/intelligence/','◇','Décision Intelligence'],
 ['track-record','/track-record/','▥','Track Record'],
 ['sources','/sources/','≋','Modèles & Données'],
 ['alerts','/alerts/','♢','Alertes & Suivi']
];
const calibration=[
 ['backtest','/backtest/','▤','Historique & Backtest'],
 ['sports','/sports/','◈','Sports Calibration'],
 ['matches','/matches/','◷','Prochains matchs']
];
const tools=[
 ['modules','/modules/','▦','Modules'],
 ['cameras','/cameras/','◎','World Eye'],
 ['settings','/settings/','⚙','Paramètres']
];
const links=rows=>rows.map(([k,href,icon,label])=>`<a href="${href}" class="${page===k?'active':''}" ${page===k?'aria-current="page"':''}><span class="icon">${icon}</span><span>${label}</span></a>`).join('');
const group=(name,rows)=>{const open=rows.some(([k])=>k===page);return `<div class="pv14-nav-group ${open?'open':''}"><button type="button" class="pv14-nav-group-toggle" aria-expanded="${open?'true':'false'}"><span>${name}</span><b>${open?'−':'+'}</b></button><nav class="pv14-nav-group-links">${links(rows)}</nav></div>`};
if(!document.querySelector('#pv14Cinematic')){const l=document.createElement('link');l.id='pv14Cinematic';l.rel='stylesheet';l.href='/providence-v14-cinematic.css?v=14.2';document.head.appendChild(l)}
if(!document.querySelector('#pv14ShellStyle')){const s=document.createElement('style');s.id='pv14ShellStyle';s.textContent=`
.pv14-nav-group{position:relative;z-index:3;border-top:1px solid rgba(73,141,199,.14);padding-top:6px;margin-top:3px}.pv14-nav-group-toggle{width:100%;border:0;background:transparent;color:#728ba4;display:flex;align-items:center;justify-content:space-between;padding:7px 10px;font-size:.5rem;letter-spacing:.13em;font-weight:850;cursor:pointer}.pv14-nav-group-toggle b{color:#48cfff;font-size:.85rem}.pv14-nav-group-links{display:none;gap:3px;padding:2px 0 7px}.pv14-nav-group.open .pv14-nav-group-links{display:grid}.pv14-nav-group-links a{height:34px;border:1px solid transparent;border-radius:7px;display:flex;align-items:center;gap:9px;padding:0 10px;text-decoration:none;color:#93aac0;font-size:.61rem}.pv14-nav-group-links a .icon{width:18px;text-align:center;color:#7fa8c9}.pv14-nav-group-links a:hover{background:rgba(22,116,210,.1)}.pv14-nav-group-links a.active{color:#fff;border-color:rgba(45,164,255,.52);background:linear-gradient(90deg,rgba(0,111,255,.28),rgba(54,51,157,.18));box-shadow:inset 3px 0 10px rgba(30,169,255,.18)}
.pv14-nav{padding-bottom:8px}.pv14-nav a{height:42px}.pv14-sidebar{overflow-y:auto;scrollbar-width:none}.pv14-sidebar::-webkit-scrollbar{display:none}.pv14-sidebar-spacer{min-height:10px}.pv14-orb{width:88px;height:88px}.pv14-mission{margin-top:3px}
@media(max-height:900px) and (min-width:981px){.pv14-nav a{height:38px}.pv14-nav{gap:2px;padding:9px 0}.pv14-orb{display:none}.pv14-mission{font-size:.57rem;padding:8px}.pv14-sidefoot{margin-top:7px}}
`;document.head.appendChild(s)}
if(!document.querySelector('.pv14-sidebar')){
 const a=document.createElement('aside');a.className='pv14-sidebar';a.innerHTML=`<a class="pv14-brand" href="/"><span class="pv14-mark" aria-hidden="true"></span><span><strong>PROVIDENCE</strong><small>VOIR · ANTICIPER · DÉCIDER.</small></span></a><nav class="pv14-nav" aria-label="Navigation Providence">${links(core)}</nav>${group('PREUVE & CALIBRATION',calibration)}${group('OUTILS',tools)}<div class="pv14-sidebar-spacer"></div><div class="pv14-orb" aria-hidden="true"></div><div class="pv14-mission"><strong>Notre mission</strong><b>Voir ce qui vient.</b><br>Mesurer l’incertitude.<br>Décider avant les autres.</div><div class="pv14-sidefoot">© 2026 Providence AI<br>Tous droits réservés.<div class="pv14-status"><i></i>Système opérationnel</div></div>`;document.body.prepend(a);
 a.querySelectorAll('.pv14-nav-group-toggle').forEach(t=>t.addEventListener('click',()=>{const box=t.closest('.pv14-nav-group');const open=box.classList.toggle('open');t.setAttribute('aria-expanded',String(open));t.querySelector('b').textContent=open?'−':'+'}));
}
if(!document.querySelector('.pv14-profile')){const p=document.createElement('div');p.className='pv14-profile';p.innerHTML='<span class="tiny">☼</span><span class="tiny">♢<sup style="color:#38adff;font-size:.55rem">8</sup></span><span><strong>Analyste Providence</strong><small><b>◆</b> Système Live</small></span><span class="badge">△</span>';document.body.appendChild(p)}
const main=document.querySelector('main');if(main)main.classList.add('pv14-main');
const hero=document.querySelector('.pv14-hero,.sports-hero,.pv-product-hero,.v5-hero,.v4-page-hero,.causal-hero,.future-hero');
if(hero&&!hero.querySelector('.pv14-art')){const art=document.createElement('div');art.className='pv14-art';art.setAttribute('aria-hidden','true');art.innerHTML='<span class="globe"></span><span class="reticle"></span><span class="satellite"></span><span class="scan"></span>';hero.prepend(art)}
})();