(() => {
  'use strict';
  function convergenceBadges(card){
    if(card.querySelector('.v13-convergence-badges')) return;
    const detail=card.querySelector('.v4-detail');
    const text=detail?.textContent||'';
    const counts=text.match(/(\d+) signal\(s\) indépendants fortement compatibles et (\d+) signal\(s\) faibles\/contextuels/i);
    const delta=text.match(/ajoute ([0-9]+(?:[.,][0-9]+)?) point\(s\)/i);
    const noDelta=/signaux faibles seuls ne modifient pas la probabilité/i.test(text);
    if(!counts&&!delta&&!noDelta) return;
    const strong=counts?Number(counts[1]):0,weak=counts?Number(counts[2]):0,d=delta?delta[1].replace(',','.'):'0';
    const target=card.querySelector('.v4-card-top')||card.querySelector('h3');if(!target)return;
    const box=document.createElement('div');box.className='v13-convergence-badges';
    box.innerHTML=`<span class="strong">${strong} fort${strong>1?'s':''}</span><span class="weak">${weak} faible${weak>1?'s':''}</span><span class="delta ${Number(d)>0?'up':'flat'}">Δ ${Number(d)>0?'+':''}${d} pt${Number(d)>1?'s':''}</span>`;
    target.insertAdjacentElement('afterend',box);
  }
  function enhance(root=document){
    root.querySelectorAll('.v4-card').forEach(card=>{
      convergenceBadges(card);
      if(card.dataset.decisionEnhanced==='1') return;
      const detail=card.querySelector('[data-detail]');
      const key=detail?.dataset?.detail;
      const bottom=card.querySelector('.v4-card-bottom');
      if(!key||!bottom) return;
      const a=document.createElement('a');
      a.href=`/intelligence/?scenario=${encodeURIComponent(key)}`;
      a.className='v4-analysis';
      a.textContent='Décider →';
      a.style.textDecoration='none';
      a.style.marginLeft='8px';
      bottom.appendChild(a);
      card.dataset.decisionEnhanced='1';
    });
  }
  enhance();
  const observer=new MutationObserver(m=>{for(const x of m)for(const n of x.addedNodes)if(n.nodeType===1)enhance(n)});
  observer.observe(document.body,{subtree:true,childList:true});
})();