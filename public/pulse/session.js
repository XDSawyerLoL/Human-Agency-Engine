import { TOKEN_KEY, state, dom, initials, api } from './core.js?v=21';

const PRESENCE_RENEW_MS=5000;
const PRESENCE_PROBE_MS=1000;
const USER_CACHE_KEY='quantic_pulse_user_cache_v1';
let presenceGuardTimer=null;
let presenceBusy=false;
let lastPresenceRenewal=0;

export async function ensureIdentityVault(){
  const status=document.querySelector('[data-pulse-id-status]');
  const title=status?.querySelector('[data-pulse-id-title]');
  const detail=status?.querySelector('[data-pulse-id-detail]');
  const submit=document.querySelector('.pulse-auth-submit');
  if(status){status.dataset.state='checking';if(title)title.textContent='Vérification d’Identity Vault…';if(detail)detail.textContent='Recherche de Quantic Identity Vault sur cet appareil.'}
  if(submit)submit.disabled=true;
  if(!window.QuanticID?.probe){
    if(status){status.dataset.state='missing';if(title)title.textContent='Quantic ID indisponible';if(detail)detail.textContent='Le runtime d’identité n’est pas chargé.'}
    return null;
  }
  const result=await window.QuanticID.probe();
  if(result.ok){
    if(status){status.dataset.state='ready';if(title)title.textContent='Identity Vault actif';if(detail)detail.textContent=(result.label||'Quantic ID')+' · preuve requise à la validation.'}
    if(submit)submit.disabled=false;
    return result;
  }
  if(status){
    status.dataset.state=result.installed?'inactive':'missing';
    if(title)title.textContent=result.installed?'Identity Vault verrouillé':'Identity Vault requis';
    if(detail)detail.textContent=result.installed?'Activez votre identité dans Identity Vault puis réessayez.':'Installez Identity Vault sur ce PC ou lancez la version portable depuis une clé USB.';
  }
  return null;
}

export async function openAuth(mode='login'){
  state.authMode=mode;
  dom.authModal.hidden=false;
  updateAuthModal();
  await ensureIdentityVault();
  setTimeout(function(){const target=state.authMode==='register'?document.getElementById('auth-handle'):document.querySelector('.pulse-auth-submit');target?.focus()},20);
}

export function closeAuth(){
  dom.authModal.hidden=true;
  dom.authError.textContent='';
}

export function updateAuthModal(){
  const register=state.authMode==='register';
  document.getElementById('auth-title').textContent=register?'Créer avec Quantic ID':'Entrer avec Quantic ID';
  document.getElementById('auth-copy').textContent=register?'Choisis ton @pseudo et ton nom affiché. Identity Vault devient la clé de ce compte.':'Identity Vault confirme directement ton compte ZOON et restaure ta session.';
  document.getElementById('display-name-field').hidden=!register;
  const handleField=document.getElementById('handle-field');
  handleField.hidden=!register;
  document.getElementById('auth-switch').textContent=register?'J’ai déjà un compte':'Créer un compte';
  document.querySelector('.pulse-auth-submit').textContent=register?'Créer mon compte':'Entrer avec Quantic ID';
}

export function updateAccount(){
  const user=state.user;
  const name=document.getElementById('account-name');
  const handle=document.getElementById('account-handle');
  const avatar=document.getElementById('account-avatar');
  const composerAvatar=document.getElementById('composer-avatar');
  const button=document.getElementById('auth-button');

  if(user){
    name.textContent=user.displayName;
    handle.textContent='@'+user.handle;
    avatar.textContent=initials(user);
    composerAvatar.textContent=initials(user);
    button.textContent='@'+user.handle;
    dom.textarea.placeholder='Écrivez une publication…';
    dom.followingLabel.textContent='Abonnements';
    dom.followingHelp.textContent='Les comptes que vous suivez';
  }else{
    name.textContent='Quantic ID';
    handle.textContent='Entrer dans ZOON';
    avatar.textContent='?';
    composerAvatar.textContent='?';
    button.textContent='Entrer';
    dom.textarea.placeholder='Écrivez une publication…';
    dom.followingLabel.textContent='Récent';
    dom.followingHelp.textContent='Les publications les plus récentes';
  }

  if(state.view==='home'){
    dom.composer.hidden=!user;
    dom.welcome.hidden=!!user;
  }
}

export function requireAuth(){
  if(state.user)return true;
  openAuth('login');
  return false;
}

function cacheLocalUser(identityKeyId=''){
  if(!state.user)return;
  try{
    localStorage.setItem(USER_CACHE_KEY,JSON.stringify({
      identityKeyId:String(identityKeyId||''),
      user:state.user,
      cachedAt:new Date().toISOString()
    }));
  }catch{}
}
async function cacheLocalUserFromVault(){
  try{
    const identity=window.QuanticID?.probe?await window.QuanticID.probe({timeoutMs:1000}):null;
    if(identity?.ok&&identity.keyId)cacheLocalUser(identity.keyId);
  }catch{}
}
function restoreCachedUser(identity){
  try{
    const cached=JSON.parse(localStorage.getItem(USER_CACHE_KEY)||'null');
    if(!cached?.user||!identity?.ok||!identity.keyId||cached.identityKeyId!==identity.keyId)return false;
    state.user=cached.user;
    updateAccount();
    return true;
  }catch{return false}
}
export function applySession(data){
  state.token=data.token;
  state.user=data.user;
  localStorage.setItem(TOKEN_KEY,data.token);
  lastPresenceRenewal=Date.now();
  updateAccount();
  void cacheLocalUserFromVault();
}

export function clearSession(forgetCachedUser=false){
  state.token='';
  state.user=null;
  lastPresenceRenewal=0;
  localStorage.removeItem(TOKEN_KEY);
  if(forgetCachedUser)localStorage.removeItem(USER_CACHE_KEY);
  updateAccount();
}

async function revokePulseSession(){
  if(state.token){
    try{await api('/api/pulse/auth/logout',{method:'POST',body:'{}'})}catch{}
  }
  clearSession();
}

export async function renewIdentityPresence({quiet=false}={}){
  if(!state.token)return false;
  if(!window.QuanticID?.probe||!window.QuanticID?.assert){
    await revokePulseSession();
    return false;
  }
  try{
    const identity=await window.QuanticID.probe({timeoutMs:1000});
    if(!identity?.ok){
      await revokePulseSession();
      return false;
    }
    const challenge=await api('/api/pulse/auth/presence/challenge',{method:'POST',body:'{}'});
    const proof=await window.QuanticID.assert({challenge:challenge.challenge,audience:challenge.audience,timeoutMs:2500});
    await api('/api/pulse/auth/presence',{method:'POST',body:JSON.stringify({identityProof:proof})});
    lastPresenceRenewal=Date.now();
    return true;
  }catch(error){
    if(!quiet)console.warn('Pulse Quantic ID presence renewal failed');
    const fatal=error?.status===401||['identity_mismatch','identity_not_registered','identity_proof_invalid'].includes(error?.message);
    if(fatal)await revokePulseSession();
    return false;
  }
}

async function presenceGuardTick(){
  if(presenceBusy||!state.token)return;
  presenceBusy=true;
  try{
    const identity=window.QuanticID?.probe?await window.QuanticID.probe({timeoutMs:900}):null;
    if(!identity?.ok){
      await revokePulseSession();
      return;
    }
    if(Date.now()-lastPresenceRenewal>=PRESENCE_RENEW_MS){
      await renewIdentityPresence({quiet:true});
    }
  }catch{
    // A central Pulse outage must not destroy the local Quantic identity session.
  }finally{
    presenceBusy=false;
  }
}

export function startIdentityPresenceGuard(){
  if(presenceGuardTimer)clearInterval(presenceGuardTimer);
  presenceGuardTimer=setInterval(presenceGuardTick,PRESENCE_PROBE_MS);
  presenceGuardTick();
}

export function stopIdentityPresenceGuard(){
  if(presenceGuardTimer)clearInterval(presenceGuardTimer);
  presenceGuardTimer=null;
}

async function restoreFromIdentity(){
  if(!window.QuanticID?.probe||!window.QuanticID?.assert)return false;
  try{
    const identity=await window.QuanticID.probe();
    if(!identity?.ok)return false;
    const challenge=await api('/api/pulse/auth/challenge',{method:'POST',body:JSON.stringify({action:'login',handle:''})});
    const proof=await window.QuanticID.assert({challenge:challenge.challenge,audience:challenge.audience});
    const data=await api('/api/pulse/auth/login',{method:'POST',body:JSON.stringify({identityProof:proof,provision:true,displayName:identity.label||'Membre Quantic'})});
    applySession(data);
    return true;
  }catch(error){
    if(error?.message!=='identity_not_registered'){
      console.warn('Pulse identity session restore failed');
    }
    return false;
  }
}

export async function restoreSession(){
  const identity=window.QuanticID?.probe?await window.QuanticID.probe({timeoutMs:1200}).catch(()=>null):null;
  if(state.token){
    const presenceOk=await renewIdentityPresence({quiet:true});
    if(presenceOk){
      try{
        const data=await api('/api/pulse/me');
        state.user=data.user;
        updateAccount();
        cacheLocalUser(identity?.keyId||'');
        return true;
      }catch(error){
        if(error?.status===401)clearSession();
        else if(restoreCachedUser(identity))return true;
      }
    }else if(state.token&&restoreCachedUser(identity)){
      return true;
    }
  }

  const restored=await restoreFromIdentity();
  if(restored)return true;
  if(restoreCachedUser(identity))return true;
  updateAccount();
  return false;
}
