(() => {
  'use strict';
  function enhance(root=document){
    root.querySelectorAll('.v4-card').forEach(card=>{
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
  const observer=new MutationObserver(m=>{ for(const x of m) for(const n of x.addedNodes) if(n.nodeType===1) enhance(n); });
  observer.observe(document.body,{subtree:true,childList:true});
})();