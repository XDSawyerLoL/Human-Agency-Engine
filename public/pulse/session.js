import { TOKEN_KEY, state, dom, initials, api } from './core.js?v=7';

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
  document.getElementById('auth-copy').textContent=register?'Choisis ton @pseudo et ton nom affiché. Identity Vault devient la clé de ce compte.':'Identity Vault confirme directement ton compte Pulse et restaure ta session.';
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
    handle.textContent='Entrer dans Pulse';
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
  if(state.token){
    try{
      const data=await api('/api/pulse/me');
      state.user=data.user;
      updateAccount();
      return true;
    }catch{
      state.token='';
      state.user=null;
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  const restored=await restoreFromIdentity();
  if(!restored)updateAccount();
  return restored;
}
