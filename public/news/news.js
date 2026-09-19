(()=>{'use strict';
const FEEDS=[
  'https://raw.githubusercontent.com/XDSawyerLoL/LEFILLIBRE/main/feed.json',
  'https://xdsawyerlol.github.io/LEFILLIBRE/feed.json'
];
const grid=document.getElementById('news-grid');
const updated=document.getElementById('news-updated');
const buttons=[...document.querySelectorAll('[data-news-filter]')];
let items=[],current='all';
const esc=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const ago=iso=>{const d=new Date(iso),m=Math.max(0,Math.round((Date.now()-d)/60000));if(!Number.isFinite(m))return'';if(m<60)return m+' min';const h=Math.floor(m/60);if(h<24)return h+' h';return d.toLocaleDateString('fr-FR',{day:'2-digit',month:'short',year:'numeric'});};
const hay=i=>`${i.category||''} ${i.source||''} ${i.title||''} ${i.summary||''}`.toLowerCase();
const eligible=i=>/\bia\b|intelligence artificielle|artificial intelligence|openai|chatgpt|anthropic|gemini|mistral|robot|tech|numéri|logiciel|cyber|cloud|ordinateur|smartphone|innovation|startup|internet|data|quantique|hardware|software|processeur|apple|google|microsoft|nvidia|amd|intel/.test(hay(i));
const match=(i,f)=>{const h=hay(i);if(f==='all')return true;if(f==='ai')return /\bia\b|intelligence artificielle|openai|chatgpt|anthropic|gemini|mistral|machine learning|cloud|cyber|logiciel/.test(h);if(f==='robot')return /robot|robotique|humanoïde|drone|automatisation/.test(h);if(f==='product')return /produit|app|application|smartphone|iphone|android|ordinateur|navigateur|logiciel|plateforme|apple|google|microsoft|nvidia|amd|intel/.test(h);if(f==='future')return /innovation|futur|recherche|prototype|startup|laboratoire|quantique|espace|énergie|mobilité/.test(h);return true;};
async function fetchFeed(){let last;for(const url of FEEDS){try{const r=await fetch(url+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();if(!Array.isArray(j.items))throw new Error('bad feed');return j;}catch(e){last=e;}}throw last||new Error('flux indisponible');}
function render(){const list=items.filter(i=>match(i,current));grid.innerHTML=list.length?list.map(i=>`<article class="q-news-card"><div class="q-news-meta"><span>${esc(i.source||'Source')}</span><span>•</span><span>${ago(i.publishedAt)}</span>${i.category?`<span>•</span><span>${esc(i.category)}</span>`:''}</div><h2>${esc(i.title||'Actualité')}</h2><p>${esc(String(i.summary||'').slice(0,240))}${String(i.summary||'').length>240?'…':''}</p><div class="q-news-actions">${i.url?`<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">Lire la source ↗</a>`:''}<a href="/pulse/">Partager sur Pulse →</a></div></article>`).join(''):'<div class="q-news-empty">Aucune actualité ne correspond à ce filtre.</div>';}
async function load(){grid.innerHTML='<div class="q-news-empty">Chargement de Quantic News…</div>';try{const data=await fetchFeed();items=(data.items||[]).filter(eligible).sort((a,b)=>new Date(b.publishedAt)-new Date(a.publishedAt)).slice(0,60);updated.textContent=(items.length||0)+' actualités · '+(data.updatedAt?'mis à jour '+ago(data.updatedAt):'flux actif');render();}catch(e){updated.textContent='Flux indisponible';grid.innerHTML='<div class="q-news-empty q-news-error">Impossible de charger Quantic News.<br><button class="q-news-retry" type="button">Réessayer</button></div>';grid.querySelector('.q-news-retry')?.addEventListener('click',load);}}
buttons.forEach(b=>b.addEventListener('click',()=>{buttons.forEach(x=>x.classList.remove('active'));b.classList.add('active');current=b.dataset.newsFilter||'all';render();}));
load();
})();