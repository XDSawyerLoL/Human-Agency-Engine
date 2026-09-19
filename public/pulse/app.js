import { TOKEN_KEY, state, dom, api, errorText } from './core.js';
import { openAuth, closeAuth, updateAuthModal, updateAccount, requireAuth, applySession, clearSession, restoreSession } from './session.js';
import { setView, loadHome, loadExplore, loadCircles, loadNotifications, loadSaved, loadProfile, loadMessages, loadConversation, loadCirclePreview } from './views.js';

function setReply(postId,handle){
  state.replyTo=postId;
  const context=document.getElementById('pulse-context');
  context.hidden=false;
  context.textContent='Réponse à @'+handle;
  document.getElementById('cancel-context').hidden=false;
  dom.textarea.focus();
}

function clearReply(){
  state.replyTo=null;
  document.getElementById('pulse-context').hidden=true;
  document.getElementById('cancel-context').hidden=true;
}

async function publishPost(){
  if(!requireAuth())return;
  const body=dom.textarea.value.trim();
  if(!body)return;
  dom.publish.disabled=true;
  try{
    await api('/api/pulse/posts',{method:'POST',body:JSON.stringify({body,replyToId:state.replyTo})});
    dom.textarea.value='';
    dom.count.textContent='0 / 420';
    clearReply();
    await loadHome();
  }catch(error){
    alert(errorText(error));
    dom.publish.disabled=false;
  }
}

async function toggleAction(postId,action){
  if(!requireAuth())return;
  try{
    await api('/api/pulse/posts/'+encodeURIComponent(postId)+'/'+action,{method:'POST',body:'{}'});
    if(state.view==='home')await loadHome();
  }catch(error){
    alert(errorText(error));
  }
}

async function reportPost(postId){
  if(!requireAuth())return;
  const reason=prompt('Pourquoi signales-tu cette publication ?');
  if(!reason)return;
  try{
    await api('/api/pulse/report',{method:'POST',body:JSON.stringify({targetType:'post',targetId:postId,reason})});
    alert('Signalement transmis.');
  }catch(error){
    alert(errorText(error));
  }
}

async function doLogout(){
  try{await api('/api/pulse/auth/logout',{method:'POST',body:'{}'})}catch{}
  clearSession();
  await loadHome();
}

async function exportData(){
  if(!requireAuth())return;
  try{
    const data=await api('/api/pulse/export');
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
    const anchor=document.createElement('a');
    anchor.href=URL.createObjectURL(blob);
    anchor.download='quantic-pulse-export.json';
    anchor.click();
    setTimeout(function(){URL.revokeObjectURL(anchor.href)},1000);
  }catch(error){
    alert(errorText(error));
  }
}

async function editProfile(){
  if(!state.user)return;
  const displayName=prompt('Nom affiché',state.user.displayName);
  if(displayName===null)return;
  const bio=prompt('Bio',state.user.bio||'');
  if(bio===null)return;
  try{
    const data=await api('/api/pulse/me',{method:'PATCH',body:JSON.stringify({displayName,bio})});
    state.user=data.user;
    updateAccount();
    await loadProfile(state.user.handle);
  }catch(error){
    alert(errorText(error));
  }
}

async function health(){
  try{
    await api('/api/pulse/health');
    document.getElementById('api-state').textContent='En ligne';
    document.getElementById('api-state').title='Service Pulse disponible';
  }catch{
    document.getElementById('api-state').textContent='Hors ligne';
  }
}

function bindStaticEvents(){
  dom.textarea.addEventListener('input',function(){
    dom.count.textContent=dom.textarea.value.length+' / 420';
    dom.publish.disabled=!dom.textarea.value.trim();
  });

  dom.publish.addEventListener('click',publishPost);
  document.getElementById('cancel-context').addEventListener('click',clearReply);
  document.getElementById('compose-focus').addEventListener('click',function(){
    if(requireAuth()){
      setView('home','Accueil');
      dom.textarea.focus();
      window.scrollTo({top:0,behavior:'smooth'});
    }
  });
  document.getElementById('mobile-compose').addEventListener('click',function(){
    if(requireAuth()){
      setView('home','Accueil');
      dom.textarea.focus();
      window.scrollTo({top:0,behavior:'smooth'});
    }
  });
  document.getElementById('auth-button').addEventListener('click',function(){
    state.user?loadProfile(state.user.handle):openAuth('login');
  });
  document.getElementById('welcome-register').addEventListener('click',function(){openAuth('register')});
  document.getElementById('welcome-login').addEventListener('click',function(){openAuth('login')});
  document.getElementById('account-button').addEventListener('click',function(){
    state.user?loadProfile(state.user.handle):openAuth('register');
  });
  document.getElementById('auth-close').addEventListener('click',closeAuth);
  document.getElementById('auth-switch').addEventListener('click',function(){
    state.authMode=state.authMode==='login'?'register':'login';
    updateAuthModal();
  });

  dom.authModal.addEventListener('click',function(event){
    if(event.target===dom.authModal)closeAuth();
  });

  dom.authForm.addEventListener('submit',async function(event){
    event.preventDefault();
    dom.authError.textContent='';
    const handle=document.getElementById('auth-handle').value.trim().replace(/^@/,'').toLowerCase();
    const password=document.getElementById('auth-password').value;
    const displayName=document.getElementById('auth-display-name').value.trim();
    try{
      const path=state.authMode==='register'?'/api/pulse/auth/register':'/api/pulse/auth/login';
      const body=state.authMode==='register'?{handle,password,displayName}:{handle,password};
      const data=await api(path,{method:'POST',body:JSON.stringify(body)});
      applySession(data);
      closeAuth();
      dom.authForm.reset();
      await loadHome();
      await loadCirclePreview();
    }catch(error){
      dom.authError.textContent=errorText(error);
    }
  });

  document.querySelectorAll('.pulse-tab').forEach(function(button){
    button.addEventListener('click',function(){
      state.feed=button.dataset.feed;
      document.querySelectorAll('.pulse-tab').forEach(function(candidate){
        candidate.classList.toggle('active',candidate===button);
      });
      loadHome();
    });
  });

  document.querySelectorAll('[data-view]').forEach(function(button){
    button.addEventListener('click',function(){
      const view=button.dataset.view;
      if(view==='home')loadHome();
      else if(view==='explore')loadExplore(document.getElementById('pulse-search').value);
      else if(view==='circles')loadCircles();
      else if(view==='notifications')loadNotifications();
      else if(view==='messages')loadMessages();
      else if(view==='saved')loadSaved();
      else if(view==='profile')loadProfile();
    });
  });

  let searchTimer;
  document.getElementById('pulse-search').addEventListener('input',function(event){
    clearTimeout(searchTimer);
    const query=event.target.value;
    searchTimer=setTimeout(function(){
      if(query.trim().length>=2)loadExplore(query);
    },250);
  });
}

function bindDelegatedEvents(){
  document.addEventListener('click',async function(event){
    const profile=event.target.closest('[data-profile]');
    if(profile){
      loadProfile(profile.dataset.profile);
      return;
    }

    const post=event.target.closest('.pulse-post');
    const action=event.target.closest('[data-action]');
    if(post&&action){
      const postId=post.dataset.id;
      if(['like','repost','bookmark'].includes(action.dataset.action)){
        toggleAction(postId,action.dataset.action);
        return;
      }
      if(action.dataset.action==='reply'){
        const handle=post.querySelector('[data-profile]')?.dataset.profile||'';
        setView('home','Accueil');
        setReply(postId,handle);
        return;
      }
      if(action.dataset.action==='share'){
        const shareUrl=location.origin+location.pathname+'?post='+encodeURIComponent(postId);
        if(navigator.share)navigator.share({title:'Quantic Pulse',url:shareUrl}).catch(function(){});
        else navigator.clipboard?.writeText(shareUrl);
        return;
      }
      if(action.dataset.action==='report'){
        reportPost(postId);
        return;
      }
    }

    const join=event.target.closest('[data-circle-join]');
    if(join){
      if(!requireAuth())return;
      try{
        await api('/api/pulse/circles/'+encodeURIComponent(join.dataset.circleJoin)+'/join',{method:'POST',body:'{}'});
        await loadCircles();
        await loadCirclePreview();
      }catch(error){alert(errorText(error))}
      return;
    }

    const follow=event.target.closest('[data-follow]');
    if(follow){
      try{
        await api('/api/pulse/users/'+encodeURIComponent(follow.dataset.follow)+'/follow',{method:'POST',body:'{}'});
        await loadProfile(follow.dataset.follow);
      }catch(error){alert(errorText(error))}
      return;
    }

    const block=event.target.closest('[data-block]');
    if(block){
      if(!confirm('Bloquer @'+block.dataset.block+' ?'))return;
      try{
        await api('/api/pulse/users/'+encodeURIComponent(block.dataset.block)+'/block',{method:'POST',body:'{}'});
        await loadHome();
      }catch(error){alert(errorText(error))}
      return;
    }

    const message=event.target.closest('[data-message-user]');
    if(message){
      loadConversation(message.dataset.messageUser);
      return;
    }

    const conversation=event.target.closest('[data-conversation]');
    if(conversation){
      loadConversation(conversation.dataset.conversation);
      return;
    }

    if(event.target.closest('[data-export]')){exportData();return}
    if(event.target.closest('[data-profile-edit]')){editProfile();return}
    if(event.target.closest('[data-logout]')){doLogout();return}
  });

  document.addEventListener('submit',async function(event){
    if(event.target.id==='circle-create'){
      event.preventDefault();
      if(!requireAuth())return;
      const form=new FormData(event.target);
      try{
        await api('/api/pulse/circles',{method:'POST',body:JSON.stringify({name:form.get('name'),description:form.get('description')})});
        await loadCircles();
        await loadCirclePreview();
      }catch(error){alert(errorText(error))}
    }

    if(event.target.id==='new-message'){
      event.preventDefault();
      const form=new FormData(event.target);
      try{
        await api('/api/pulse/messages',{method:'POST',body:JSON.stringify({handle:String(form.get('handle')||'').replace(/^@/,''),body:form.get('body')})});
        await loadMessages();
      }catch(error){alert(errorText(error))}
    }

    if(event.target.id==='conversation-form'){
      event.preventDefault();
      const form=new FormData(event.target);
      const handle=event.target.dataset.handle;
      try{
        await api('/api/pulse/messages',{method:'POST',body:JSON.stringify({handle,body:form.get('body')})});
        await loadConversation(handle);
      }catch(error){alert(errorText(error))}
    }
  });
}

async function init(){
  bindStaticEvents();
  bindDelegatedEvents();
  await health();
  await restoreSession();
  await Promise.all([loadHome(),loadCirclePreview()]);
}

init();
