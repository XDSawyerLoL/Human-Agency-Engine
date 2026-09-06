(()=>{'use strict';
function patch(){
  const root=document.querySelector('#worlds');if(!root)return;
  for(const card of root.querySelectorAll('.pa-world')){
    const h=card.querySelector('h3');if(!h)continue;const title=String(h.textContent||'').trim();
    const label=card.querySelector('header span'),metric=card.querySelector('.prob span:first-child'),foot=card.querySelector('small');
    if(/^Victoire finale\s*:/i.test(title)){
      if(label)label.textContent='RÉSULTAT FINAL';
      const strong=metric?.querySelector('strong');if(metric&&strong){const value=strong.textContent;metric.innerHTML=`Probabilité de victoire <strong>${value}</strong>`;}
      if(foot)foot.textContent='Projection probabiliste assemblée · les déductions et duels inférés restent distingués des observations.';
      card.classList.add('pa-final-election');
    }else if(/^Issue (?:encore )?non résolue/i.test(title)){
      if(label)label.textContent='INCERTITUDE';
      if(metric)metric.textContent='Masse de probabilité non résolue';
      if(foot)foot.textContent='Providence ne redistribue pas artificiellement cette masse.';
    }
  }
}
function boot(){const root=document.querySelector('#worlds');if(!root)return;patch();new MutationObserver(()=>patch()).observe(root,{childList:true,subtree:true});}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
