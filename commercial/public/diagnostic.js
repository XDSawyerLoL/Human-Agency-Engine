// Auto-évaluation heuristique : aucune donnée personnelle ni transmission réseau.
export const riskLabels = Object.freeze({
  energy:'une interruption énergétique',
  supply:'une rupture d’approvisionnement',
  weather:'un épisode météorologique perturbateur',
  transport:'une perturbation des transports'
});
export const actionLibrary = Object.freeze({
  energy:'Vérifier les dépendances électriques prioritaires, les besoins de continuité et les alternatives adaptées aux équipements critiques.',
  supply:'Lister les composants et prestations sans fournisseur alternatif et documenter les délais réalistes de substitution.',
  weather:'Consulter les alertes officielles pour les sites concernés et définir des consignes de protection et de déplacement.',
  transport:'Identifier les trajets et livraisons critiques, puis préparer des alternatives avec vos transporteurs et équipes.'
});
export function evaluateDiagnostic(input) {
  const sector=String(input.sector||''),risk=String(input.risk||''),resilience=String(input.resilience||'');
  const sectors=new Set(['commerce','production','logistique','services','batiment']);
  if(!sectors.has(sector)||!riskLabels[risk]||!new Set(['short','medium','long','unknown']).has(resilience)) throw new Error('Réponses manquantes ou invalides.');
  const flags={backup:input.backup===true,plan:input.plan===true,monitor:input.monitor===true};
  const prepared=Object.values(flags).filter(Boolean).length;
  const actions=[actionLibrary[risk]];
  if(!flags.plan) actions.push('Rédiger une procédure courte : qui décide, qui prévenir et quelles opérations interrompre ou maintenir.');
  if(!flags.backup) actions.push('Identifier un scénario de repli et vérifier qu’il fonctionne avec les personnes ou partenaires concernés.');
  if(!flags.monitor) actions.push('Désigner un responsable de veille, les sources officielles à consulter et un rythme de vérification.');
  if(resilience==='unknown') actions.push('Estimer le temps maximal acceptable d’interruption pour une activité essentielle et documenter cette hypothèse.');
  if(resilience==='short') actions.push('Préparer les premières 24 heures : sécurité des personnes, contacts prioritaires et procédures de réaction.');
  if(actions.length<3) actions.push('Tester le scénario de continuité lors d’un exercice court et mettre à jour les rôles et coordonnées.');
  if(actions.length<3) actions.push('Définir une date de révision et un responsable pour chaque mesure.');
  return {
    preparednessCount:prepared,
    title:'Préparer votre entreprise à '+riskLabels[risk],
    summary:resilience==='unknown'?'Vous n’avez pas encore estimé votre marge d’interruption. Le premier objectif est de la préciser.':resilience==='short'?'Une interruption de moins de 24 heures pourrait imposer des décisions rapides.':resilience==='medium'?'Votre marge déclarée est de 1 à 3 jours : vérifiez les hypothèses et les dépendances.':'Votre marge déclarée dépasse trois jours : validez-la sur chaque fonction essentielle.',
    preparednessLabel:`${prepared} mesure${prepared>1?'s':''} déclarée${prepared>1?'s':''} sur 3 — ce n’est pas une note de risque`,
    actions:actions.slice(0,3)
  };
}
if(typeof document !== 'undefined'){
  const form=document.querySelector('#assessmentForm');
  form?.addEventListener('submit',event=>{
    event.preventDefault();
    const data=new FormData(form);
    const o={sector:data.get('sector'),risk:data.get('risk'),resilience:data.get('resilience'),backup:data.has('backup'),plan:data.has('plan'),monitor:data.has('monitor')};
    try {
      const answer=evaluateDiagnostic(o);
      const result=document.querySelector('#results');
      document.querySelector('#resultTitle').textContent=answer.title;
      document.querySelector('#resultSummary').textContent=answer.summary;
      document.querySelector('#resultPrepared').textContent=answer.preparednessLabel;
      const list=document.querySelector('#resultActions');list.replaceChildren();
      answer.actions.forEach(action=>{const li=document.createElement('li');li.textContent=action;list.append(li)});
      result.hidden=false;
      result.scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){alert(e.message)}
  });
  document.querySelector('#printDiagnostic')?.addEventListener('click',()=>window.print());
}