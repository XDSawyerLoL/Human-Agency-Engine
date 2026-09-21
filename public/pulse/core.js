export const API_BASE=String(window.QUANTIC_PULSE_API_BASE||'').replace(/\/$/,'');
export const TOKEN_KEY='quantic_pulse_token';
export const state={token:localStorage.getItem(TOKEN_KEY)||'',user:null,feed:'following',view:'home',replyTo:null,authMode:'login',attachment:null};

export const dom={
  feed:document.getElementById('pulse-feed'),
  textarea:document.getElementById('pulse-text'),
  publish:document.getElementById('pulse-publish'),
  count:document.getElementById('pulse-count'),
  composer:document.getElementById('composer'),
  feedTabs:document.getElementById('feed-tabs'),
  viewTitle:document.getElementById('view-title'),
  authModal:document.getElementById('auth-modal'),
  authForm:document.getElementById('auth-form'),
  authError:document.getElementById('auth-error'),
  welcome:document.getElementById('pulse-welcome'),
  followingLabel:document.getElementById('feed-following-label'),
  followingHelp:document.getElementById('feed-following-help')
};

export function esc(v){
  return String(v||'').replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c];
  });
}

export function icon(name,extra=''){
  return '<svg class="pi '+extra+'" aria-hidden="true"><use href="#'+name+'"></use></svg>';
}

export function initials(user){
  const value=(user?.displayName||user?.handle||'?').trim().split(/\s+/).slice(0,2).map(function(x){return x[0]||''}).join('');
  return value.toUpperCase()||'?';
}

export function timeAgo(iso){
  const t=Date.parse(iso),d=Math.max(0,Date.now()-t),m=Math.floor(d/60000);
  if(m<1)return'maintenant';
  if(m<60)return m+' min';
  const h=Math.floor(m/60);
  if(h<24)return h+' h';
  const days=Math.floor(h/24);
  if(days<7)return days+' j';
  return new Date(t).toLocaleDateString('fr-FR',{day:'2-digit',month:'short'});
}

export function setStatus(title,text){
  dom.feed.innerHTML='<div class="pulse-status"><strong>'+esc(title)+'</strong>'+esc(text||'')+'</div>';
}

export function errorText(e){
  const map={
    unauthorized:'Connexion requise.',
    handle_taken:'Cet identifiant est déjà pris.',
    invalid_handle:'Identifiant : 3 à 24 caractères, lettres minuscules, chiffres ou _.',
    rate_limited:'Trop de requêtes. Réessaie plus tard.',
    not_found:'Élément introuvable.',
    blocked:'Cette conversation est bloquée.',
    network_error:'Connexion au service Pulse impossible. Recharge la page puis réessaie.',
    request_failed:'La requête Pulse a échoué. Réessaie dans un instant.',
    pulse_storage_unavailable:'Le stockage Pulse est momentanément indisponible. Tes données ne sont pas remplacées par un état vide ; réessaie dans un instant.',
    'fetch failed':'Le stockage Pulse a rencontré une coupure temporaire. Réessaie dans un instant.',
    identity_vault_required:'Quantic Identity Vault est requis pour créer un compte ou se connecter.',
    identity_proof_required:'Identity Vault doit signer cette connexion.',
    identity_proof_invalid:'La preuve Identity Vault est invalide.',
    identity_challenge_expired:'La vérification Identity Vault a expiré. Réessaie.',
    identity_challenge_mismatch:'La preuve Identity Vault ne correspond pas à cette connexion.',
    identity_mismatch:'Ce compte Pulse est lié à une autre identité Quantic.',
    identity_already_linked:'Cette identité Quantic est déjà liée à un compte Pulse.',
    identity_not_registered:'Aucun compte Pulse n’est encore lié à cette identité Quantic.'
  };
  return map[e?.message]||e?.message||'Une erreur est survenue.';
}

export async function api(path,options={}){
  const headers={'content-type':'application/json',...(options.headers||{})};
  if(state.token)headers.authorization='Bearer '+state.token;
  let response;
  try{
    response=await fetch(API_BASE+path,{...options,headers});
  }catch(cause){
    const err=new Error('network_error');
    err.cause=cause;
    throw err;
  }
  const data=await response.json().catch(function(){return{}});
  if(!response.ok){
    const err=new Error(data.error||'request_failed');
    err.status=response.status;
    err.data=data;
    throw err;
  }
  return data;
}
