(() => {
  const form=document.querySelector('#contactForm');
  if(!form)return;
  const params=new URLSearchParams(location.search);
  for(const link of document.querySelectorAll('[data-plan]'))link.addEventListener('click',()=>{form.querySelector('[name="interest"]').value='pilot';form.querySelector('[name="details"]').value='Offre pilote '+link.dataset.plan+' : ';});
  form.addEventListener('submit', async event=>{
    event.preventDefault();const status=document.querySelector('#formStatus'),button=document.querySelector('#sendBtn');
    status.className='form-status';status.textContent='Enregistrement de votre demande...';button.disabled=true;
    const fields=Object.fromEntries(new FormData(form).entries());
    const body={...fields,accepted_privacy:form.elements.accepted_privacy.checked,consent_marketing:form.elements.consent_marketing.checked,utm_source:params.get('utm_source')||'',utm_medium:params.get('utm_medium')||'',utm_campaign:params.get('utm_campaign')||'',source:'horizon-b2b'};
    try{
      const res=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await res.json();if(!res.ok||!data.ok)throw Error(data.error||'Envoi non confirmé');
      status.className='form-status ok';status.textContent='Votre demande a bien été enregistrée.';form.reset();
    }catch(error){status.className='form-status error';status.textContent=error.message||'Service temporairement indisponible.';}
    finally{button.disabled=false;}
  });
})();