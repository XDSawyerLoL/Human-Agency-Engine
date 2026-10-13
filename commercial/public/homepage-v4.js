/** HORIZON illustrative scenarios. No live observations, no external API. */
(() => {
  const cases = Object.freeze({
    transport: {
      sector:'Transport & logistique',title:'Conditions météo défavorables sur une zone de livraison',
      description:'Un bulletin officiel fait état d’un épisode météo pouvant concerner certains itinéraires. L’impact sur les tournées reste à établir selon les horaires et les zones desservies.',
      source:'Vigilance météo — source officielle',evidence:'Source identifiée, impact non confirmé',
      routeSource:'Bulletin publié',routeAction:'Vérifier les tournées',impact:'Retards de livraison',
      impactDescription:'Risque à examiner selon les créneaux, itinéraires et engagements client.',
      actions:['Comparer les tournées aux zones concernées.','Identifier les clients à prévenir en cas de retard.','Préparer des itinéraires de repli.']
    },
    industrie: {
      sector:'Industrie & production',title:'Signal de tension sur une ressource énergétique',
      description:'Une information d’exploitation publiée par un opérateur d’énergie indique une situation à surveiller. Aucun arrêt de production n’est présumé : l’exposition dépend des contrats et des sites.',
      source:'Information d’exploitation — source officielle',evidence:'Signal à contextualiser, conséquences inconnues',
      routeSource:'Donnée publiée',routeAction:'Vérifier les dépendances',impact:'Continuité des équipements',
      impactDescription:'Un arrêt éventuel ne peut être établi sans informations propres aux installations.',
      actions:['Identifier les machines et processus critiques.','Vérifier les solutions d’alimentation alternatives.','Confirmer les seuils d’alerte avec l’exploitant.']
    },
    commerce: {
      sector:'Commerce & distribution',title:'Perturbation potentielle d’une chaîne d’approvisionnement',
      description:'Plusieurs signalements évoquent une difficulté logistique. Ils ne prouvent pas une rupture chez un fournisseur donné : une vérification directe est nécessaire.',
      source:'Sources publiques — signalements à recouper',evidence:'Hypothèse, confirmation fournisseur absente',
      routeSource:'Signalements',routeAction:'Contrôler les stocks',impact:'Disponibilité de produits',
      impactDescription:'Impact possible sur les références les plus dépendantes d’un seul fournisseur.',
      actions:['Vérifier les références à couverture de stock faible.','Interroger les fournisseurs concernés.','Identifier les produits ou circuits alternatifs.']
    }
  });
  const bind = {
    'sector-name':'sector','signal-title':'title','signal-description':'description',
    'signal-source':'source','signal-evidence':'evidence','route-source':'routeSource',
    'route-action':'routeAction','impact-title':'impact','impact-description':'impactDescription'
  };
  const tabs=[...document.querySelectorAll('[data-sector]')];
  const actions=document.querySelector('#actions-list');
  function selectScenario(name){
    const item=cases[name]; if(!item) return;
    for(const [id,key] of Object.entries(bind)){const node=document.getElementById(id);if(node)node.textContent=item[key];}
    if(actions){actions.replaceChildren(...item.actions.map((t)=>{const li=document.createElement('li');li.textContent=t;return li;}));}
    for(const button of tabs){const active=button.dataset.sector===name;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));}
    const board=document.querySelector('.scenario-board');if(board)board.setAttribute('data-scenario',name);
  }
  for(const button of tabs) button.addEventListener('click',()=>selectScenario(button.dataset.sector));
  selectScenario('transport');
})();