import { TOKEN_KEY, state, dom, initials, api } from './core.js';

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
  setTimeout(function(){document.getElementById('auth-handle').focus()},20);
}

export function closeAuth(){
  dom.authModal.hidden=true;
  dom.authError.textContent='';
}

export function updateAuthModal(){
  const register=state.authMode==='register';
  document.getElementById('auth-title').textContent=register?'Créer un compte':'Se connecter';
  document.getElementById('auth-copy').textContent=register?'Choisis ton identité Pulse. Identity Vault sera lié à ce compte.':'Retrouve ton fil, tes abonnements et tes messages. Identity Vault doit confirmer ton identité.';
  document.getElementById('display-name-field').hidden=!register;
  document.getElementById('auth-switch').textContent=register?'J’ai déjà un compte':'Créer un compte';
  document.getElementById('auth-password').autocomplete=register?'new-password':'current-password';
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
    name.textContent='Compte Pulse';
    handle.textContent='Identité locale Pulse';
    avatar.textContent='?';
    composerAvatar.textContent='?';
    button.textContent='Compte Pulse';
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

export function applySession(data){
  state.token=data.token;
  state.user=data.user;
  localStorage.setItem(TOKEN_KEY,data.token);
  updateAccount();
}

export function clearSession(){
  state.token='';
  state.user=null;
  localStorage.removeItem(TOKEN_KEY);
  updateAccount();
}

export async function restoreSession(){
  if(!state.token){
    updateAccount();
    return;
  }
  try{
    const data=await api('/api/pulse/me');
    state.user=data.user;
  }catch{
    state.token='';
    localStorage.removeItem(TOKEN_KEY);
  }
  updateAccount();
}
