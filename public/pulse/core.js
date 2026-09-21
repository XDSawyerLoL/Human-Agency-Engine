// Default to same-origin. On Hostinger, /api/pulse/* is already proxied server-side
// to the durable Pulse backend, which avoids browser CORS/preflight failures.
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
    e2ee_required:'Cette conversation exige le chiffrement de bout en bout Pulse Secure.',
    secure_recipient_unavailable:'Ce contact n’a pas encore activé Pulse Secure sur un appareil.',
    secure_device_required:'Pulse Secure doit enregistrer cet appareil avant l’envoi.',
    secure_device_invalid:'Les clés de sécurité de cet appareil sont invalides.',
    secure_device_conflict:'Les clés de cet appareil ont changé. Révoque l’ancien appareil avant de continuer.',
    secure_identity_changed:'La clé d’identité Quantic de ce contact a changé. Vérifie son numéro de sécurité avant de poursuivre.',
    secure_crypto_unsupported:'Ce navigateur ne prend pas en charge les primitives cryptographiques requises par Pulse Secure.',
    secure_sender_unverified:'La signature cryptographique de l’expéditeur ne peut pas être vérifiée.',
    secure_prekeys_invalid:'Le lot de clés à usage unique est invalide.',
    secure_prekey_signature_invalid:'La signature d’une clé à usage unique est invalide.',
    secure_prekey_unavailable:'Ce correspondant doit renouveler ses clés de sécurité avant cette étape.',
    secure_prekey_missing:'La clé locale à usage unique a déjà été consommée ou n’est plus disponible.',
    secure_network_unavailable:'Aucun transport Quantic sécurisé n’est disponible pour le moment.',
    secure_pq_downgrade:'Le niveau post-quantique déjà observé pour cet appareil a diminué. Envoi bloqué pour éviter un downgrade.',
    secure_pq_unsupported:'Ce navigateur ne prend pas encore en charge ML-KEM-768. La session hybride ne sera pas rétrogradée silencieusement.',
    secure_pq_prekey_invalid:'La clé post-quantique publiée par cet appareil est invalide.',
    secure_pq_prekey_missing:'La clé post-quantique locale requise n’est plus disponible.',
    secure_pq_handshake_invalid:'La négociation post-quantique de cette session est invalide.',
    ratchet_session_missing:'La session Double Ratchet est introuvable. Une nouvelle négociation sécurisée est nécessaire.',
    ratchet_header_invalid:'L’en-tête cryptographique du message est invalide.',
    ratchet_message_replay:'Ce message sécurisé a déjà été traité.',
    ratchet_too_many_skipped:'Trop de messages manquent dans cette session. Synchronise les appareils avant de continuer.',
    ratchet_skipped_store_full:'La réserve locale de clés pour messages désordonnés est pleine.',
    secure_protocol_mismatch:'Version Pulse Secure incompatible.',
    pulse_storage_unavailable:'Le stockage Pulse est momentanément indisponible. Tes données ne sont pas remplacées par un état vide ; réessaie dans un instant.',
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
  const method=String(options.method||'GET').toUpperCase();
  const headers={...(options.headers||{})};
  if(options.body!==undefined&&options.body!==null&&!headers['content-type'])headers['content-type']='application/json';
  if(state.token)headers.authorization='Bearer '+state.token;
  const attempts=method==='GET'?3:1;
  let lastCause=null;
  for(let attempt=0;attempt<attempts;attempt++){
    let response;
    try{
      response=await fetch(API_BASE+path,{cache:'no-store',...options,headers});
    }catch(cause){
      lastCause=cause;
      if(attempt+1<attempts){await new Promise(resolve=>setTimeout(resolve,350*(attempt+1)));continue}
      const err=new Error('network_error');err.cause=cause;throw err;
    }
    const data=await response.json().catch(function(){return{}});
    if(response.ok)return data;
    if(method==='GET'&&response.status>=500&&attempt+1<attempts){
      await new Promise(resolve=>setTimeout(resolve,350*(attempt+1)));
      continue;
    }
    const err=new Error(data.error||'request_failed');
    err.status=response.status;
    err.data=data;
    throw err;
  }
  const err=new Error('network_error');err.cause=lastCause;throw err;
}
