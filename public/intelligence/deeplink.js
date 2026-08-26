(() => {
  'use strict';
  const wanted=new URLSearchParams(location.search).get('scenario');
  if(!wanted) return;
  const safe=v=>String(v||'').replace(/[^a-zA-Z0-9_-]/g,'-');
  let tries=0;
  const timer=setInterval(()=>{
    tries++;
    const select=document.getElementById('scenarioSelect');
    if(select?.options?.length){
      const option=[...select.options].find(o=>safe(o.value)===wanted||o.value===wanted);
      if(option){ select.value=option.value; select.dispatchEvent(new Event('change',{bubbles:true})); document.querySelector('.d6-section.dossier')?.scrollIntoView({behavior:'smooth',block:'start'}); }
      clearInterval(timer);
    } else if(tries>40) clearInterval(timer);
  },150);
})();