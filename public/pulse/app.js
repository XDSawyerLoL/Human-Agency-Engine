import { TOKEN_KEY, state, dom, api, errorText, safeAvatarUrl } from './core.js?v=25';
import { openAuth, closeAuth, updateAuthModal, updateAccount, requireAuth, applySession, clearSession, restoreSession, retryIdentityConnection, ensureIdentityVault, startIdentityPresenceGuard } from './session.js?v=25';
import { setView, loadHome, loadExplore, loadVisual, loadCircles, loadCircle, loadNotifications, loadSaved, loadProfile, loadMessages, loadConversation, loadCirclePreview, loadNewsRss } from './views.js?v=25';
import { ensureSecureDevice, sendSecureMessage } from './secure.js?v=25';

function setReply(postId,handle){
  state.replyTo=postId;
  const context=document.getElementById('pulse-context');
  context.hidden=false;
  context.textContent='Réponse à @'+handle;
  document.getElementById('cancel-context').hidden=false;
  dom.textarea.focus();
}

async function identityProof(action,handle){
  const identity=await ensureIdentityVault();
  if(!identity)throw new Error('identity_vault_required');
  const challenge=await api('/api/pulse/auth/challenge',{method:'POST',body:JSON.stringify({action,handle})});
  if(!window.QuanticID?.assert)throw new Error('identity_vault_required');
  return window.QuanticID.assert({challenge:challenge.challenge,audience:challenge.audience});
}

function clearReply(){
  state.replyTo=null;
  document.getElementById('pulse-context').hidden=true;
  document.getElementById('cancel-context').hidden=true;
}

function safeHttpsUrl(value){
  try{const u=new URL(String(value||''));return u.protocol==='https:'?u.href:''}catch{return''}
}

function updateMediaPreview(){
  const box=document.getElementById('pulse-media-preview');
  if(!box)return;
  const media=state.attachment||{};
  const image=safeAvatarUrl(media.mediaUrl||media.imageUrl);
  const link=safeHttpsUrl(media.linkUrl);
  if(!image&&!link){box.hidden=true;box.innerHTML='';return}
  const label=media.mediaType==='gif'?'GIF':media.mediaType==='image'?'Photo du post':(media.linkTitle||'Aperçu');
  box.hidden=false;
  box.innerHTML=(image?'<img src="'+image.replace(/"/g,'&quot;')+'" alt="" referrerpolicy="no-referrer">':'')+
    '<div><strong>'+String(label).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))+'</strong>'+
    (link?'<span>'+link.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))+'</span>':'')+'</div>'+
    '<button type="button" data-remove-media aria-label="Retirer">×</button>';
}

async function publishPost(){
  if(!requireAuth())return;
  const caption=dom.textarea.value.trim();
  const body=caption||(state.attachment?.mediaType==='image'?'Photo':'');
  const max=Number(state.user?.maxPostLength||420);
  if(!body||Array.from(body).length>max){alert('Limite de '+max+' caractères pour votre compte.');return}
  dom.publish.disabled=true;
  try{
    await api('/api/pulse/posts',{method:'POST',body:JSON.stringify({body,replyToId:state.replyTo,...(state.attachment||{})})});
    dom.textarea.value='';
    dom.count.textContent='0 / '+(state.user?.maxPostLength||420);
    clearReply();
    state.attachment=null;
    updateMediaPreview();
    await loadHome();
  }catch(error){
    const durabilityFailure=['pulse_storage_unavailable','pulse_remote_store_unavailable','pulse_storage_conflict','network_error'].includes(error?.message);
    alert(durabilityFailure
      ? 'Publication non enregistrée : le stockage durable SOCIAL n’a pas confirmé l’écriture. Ton texte est conservé ici, tu peux réessayer.'
      : errorText(error));
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

async function deleteOwnPost(postId,postElement){
  if(!requireAuth())return;
  if(!window.confirm('Supprimer définitivement cette publication ?'))return;
  const previousHidden=postElement?.hidden||false;
  if(postElement)postElement.hidden=true;
  try{
    await api('/api/pulse/posts/'+encodeURIComponent(postId),{method:'DELETE'});
    postElement?.remove();
    if(state.view==='home')await loadHome();
  }catch(error){
    if(postElement)postElement.hidden=previousHidden;
    alert('Impossible de supprimer cette publication : '+errorText(error));
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
  clearSession(true);
  await loadHome();
}

async function exportData(){
  if(!requireAuth())return;
  try{
    const data=await api('/api/pulse/export');
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
    const anchor=document.createElement('a');
    anchor.href=URL.createObjectURL(blob);
    anchor.download='social-export.json';
    anchor.click();
    setTimeout(function(){URL.revokeObjectURL(anchor.href)},1000);
  }catch(error){
    alert(errorText(error));
  }
}

async function uploadOwnAvatar(){
  if(!requireAuth())return;
  const picker=document.createElement('input');
  picker.type='file';picker.accept='image/png,image/jpeg,image/webp';
  picker.setAttribute('aria-label','Sélectionner une photo de profil');
  picker.addEventListener('change',async()=>{
    const file=picker.files?.[0];
    if(!file)return;
    if(!/^image\/(?:png|jpeg|webp)$/.test(file.type)||file.size>5_000_000){
      alert('Utilise une image PNG, JPEG ou WebP de moins de 5 Mo.');return;
    }
    const objectURL=URL.createObjectURL(file);
    try{
      const img=await new Promise((resolve,reject)=>{
        const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('image_invalid'));image.src=objectURL;
      });
      const canvas=document.createElement('canvas');
      canvas.width=256;canvas.height=256;
      const ctx=canvas.getContext('2d');
      if(!ctx)throw new Error('image_canvas_unavailable');
      const side=Math.min(img.naturalWidth,img.naturalHeight);
      ctx.drawImage(img,(img.naturalWidth-side)/2,(img.naturalHeight-side)/2,side,side,0,0,256,256);
      let avatar='';
      for(const quality of [.76,.62,.48,.36]){
        avatar=canvas.toDataURL('image/webp',quality);
        if(avatar.startsWith('data:image/webp;')&&avatar.length<=60000)break;
      }
      if(!avatar.startsWith('data:image/webp;')||avatar.length>60000)throw new Error('image_too_large');
      const data=await api('/api/pulse/me',{method:'PATCH',body:JSON.stringify({avatar})});
      state.user=data.user;updateAccount();
      await loadProfile(state.user.handle);
    }catch(error){alert('Photo non enregistrée : '+errorText(error))}
    finally{URL.revokeObjectURL(objectURL);picker.remove()}
  },{once:true});
  picker.click();
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
    document.getElementById('api-state').title='Service SOCIAL disponible';
  }catch{
    document.getElementById('api-state').textContent='Hors ligne';
  }
}

function bindStaticEvents(){
  dom.textarea.addEventListener('input',function(){
    const max=Number(state.user?.maxPostLength||420);
    const count=Array.from(dom.textarea.value).length;
    dom.count.textContent=count+' / '+max;
    dom.publish.disabled=(!dom.textarea.value.trim()&&!state.attachment?.mediaUrl)||count>max;
  });

  dom.publish.addEventListener('click',publishPost);
  document.querySelector('[data-tool="news"]')?.addEventListener('click',function(){
    loadNewsRss();
  });
  document.querySelector('[data-tool="emoji"]')?.addEventListener('click',function(){
    const picker=document.getElementById('pulse-emoji-picker');
    picker.hidden=!picker.hidden;
  });
  document.getElementById('pulse-emoji-picker')?.addEventListener('click',function(event){
    const button=event.target.closest('[data-emoji]');
    if(!button)return;
    const emoji=button.dataset.emoji||'';
    const start=dom.textarea.selectionStart??dom.textarea.value.length;
    const end=dom.textarea.selectionEnd??start;
    dom.textarea.value=dom.textarea.value.slice(0,start)+emoji+dom.textarea.value.slice(end);
    dom.textarea.dispatchEvent(new Event('input',{bubbles:true}));
    dom.textarea.focus();
    dom.textarea.setSelectionRange(start+emoji.length,start+emoji.length);
  });
  document.addEventListener('click',function(event){
    const picker=document.getElementById('pulse-emoji-picker');
    if(!picker||picker.hidden)return;
    if(event.target.closest('[data-tool="emoji"]')||event.target.closest('#pulse-emoji-picker'))return;
    picker.hidden=true;
  });
  const gifModal=document.getElementById('pulse-gif-modal');
  const gifInput=document.getElementById('pulse-gif-url');
  const gifPreview=document.getElementById('pulse-gif-preview');
  const gifError=document.getElementById('pulse-gif-error');
  const gifInsert=document.getElementById('pulse-gif-insert');
  const closeGifModal=()=>{gifModal.hidden=true;gifInput.value='';gifPreview.innerHTML='<span>Aperçu du GIF</span>';gifError.textContent='';gifInsert.disabled=true;};
  const refreshGifPreview=()=>{
    const url=safeHttpsUrl(gifInput.value);
    gifError.textContent='';
    gifInsert.disabled=!url;
    gifPreview.innerHTML=url?'<img src="'+url.replace(/"/g,'&quot;')+'" alt="Aperçu GIF" referrerpolicy="no-referrer">':'<span>Aperçu du GIF</span>';
  };
  const photoInput=document.getElementById('social-photo-input');
  document.querySelector('[data-tool="photo"]')?.addEventListener('click',()=>{if(requireAuth())photoInput?.click()});
  photoInput?.addEventListener('change',async()=>{
    const file=photoInput.files?.[0];photoInput.value='';
    if(!file)return;
    if(!/^image\/(?:jpeg|png|webp)$/.test(file.type)||file.size>8_000_000){alert('Photo JPEG, PNG ou WebP de 8 Mo maximum.');return}
    const objectUrl=URL.createObjectURL(file);
    try{
      const image=await new Promise((resolve,reject)=>{
        const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('image_invalid'));img.src=objectUrl;
      });
      if(image.naturalWidth>10000||image.naturalHeight>10000)throw new Error('image_too_large');
      let data='';
      for(const edge of [480,420,360,300]){
        const ratio=Math.min(1,edge/Math.max(image.naturalWidth,image.naturalHeight));
        const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*ratio));canvas.height=Math.max(1,Math.round(image.naturalHeight*ratio));
        const ctx=canvas.getContext('2d');if(!ctx)throw new Error('image_canvas_unavailable');
        ctx.drawImage(image,0,0,canvas.width,canvas.height);
        for(const quality of [.78,.63,.49,.35]){
          data=canvas.toDataURL('image/webp',quality);
          if(data.startsWith('data:image/webp;')&&data.length<59000)break;
        }
        if(data.startsWith('data:image/webp;')&&data.length<59000)break;
      }
      if(!data.startsWith('data:image/webp;')||data.length>=59000)throw new Error('image_too_large');
      state.attachment={mediaUrl:data,mediaType:'image'};
      updateMediaPreview();
      dom.publish.disabled=!dom.textarea.value.trim()&&!state.attachment.mediaUrl;
    }catch(error){alert('Impossible de préparer la photo : '+errorText(error))}
    finally{URL.revokeObjectURL(objectUrl)}
  });
  document.querySelector('[data-tool="gif"]')?.addEventListener('click',function(){
    document.getElementById('pulse-emoji-picker').hidden=true;
    gifModal.hidden=false;
    setTimeout(()=>gifInput.focus(),0);
  });
  gifInput?.addEventListener('input',refreshGifPreview);
  gifPreview?.addEventListener('error',function(){gifError.textContent='Impossible d’afficher ce GIF.';gifInsert.disabled=true;},true);
  document.getElementById('pulse-gif-close')?.addEventListener('click',closeGifModal);
  document.getElementById('pulse-gif-cancel')?.addEventListener('click',closeGifModal);
  gifModal?.addEventListener('click',function(event){if(event.target===gifModal)closeGifModal();});
  gifInsert?.addEventListener('click',function(){
    const url=safeHttpsUrl(gifInput.value);
    if(!url){gifError.textContent='Utilise une adresse HTTPS valide.';return}
    state.attachment={mediaUrl:url,mediaType:'gif'};
    updateMediaPreview();
    closeGifModal();
  });
  document.getElementById('pulse-media-preview')?.addEventListener('click',function(event){
    if(!event.target.closest('[data-remove-media]'))return;
    state.attachment=null;
    updateMediaPreview();
  });
  document.getElementById('cancel-context').addEventListener('click',clearReply);
  document.getElementById('compose-focus').addEventListener('click',function(){
    if(requireAuth()){
      state.feed='following';
      document.querySelectorAll('.pulse-tab').forEach(button=>button.classList.toggle('active',button.dataset.feed==='following'));
      setView('home','Accueil');
      dom.textarea.focus();
      window.scrollTo({top:0,behavior:'smooth'});
    }
  });
  document.getElementById('mobile-compose').addEventListener('click',function(){
    if(requireAuth()){
      state.feed='following';
      document.querySelectorAll('.pulse-tab').forEach(button=>button.classList.toggle('active',button.dataset.feed==='following'));
      setView('home','Accueil');
      dom.textarea.focus();
      window.scrollTo({top:0,behavior:'smooth'});
    }
  });
  document.getElementById('auth-button').addEventListener('click',function(){
    state.user?loadProfile(state.user.handle):openAuth('login');
  });
  document.getElementById('welcome-register').addEventListener('click',function(){openAuth('register')});
  document.getElementById('welcome-login').addEventListener('click',async function(){
  if(state.identityStatus==='error'){
    if(await retryIdentityConnection()){await Promise.all([loadHome(),loadCirclePreview()]);return}
  }
  openAuth('login');
});
  document.getElementById('account-button').addEventListener('click',function(){
    state.user?loadProfile(state.user.handle):openAuth('login');
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
    const register=state.authMode==='register';
    const handle=register?document.getElementById('auth-handle').value.trim().replace(/^@/,'').toLowerCase():'';
    const displayName=register?document.getElementById('auth-display-name').value.trim():'';
    try{
      const action=register?'register':'login';
      const path=register?'/api/pulse/auth/register':'/api/pulse/auth/login';
      const proof=register?await identityProof('register',handle):await identityProof('login','');
      const activeIdentity=!register?await ensureIdentityVault():null;
      const body=register?{handle,displayName,identityProof:proof}:{identityProof:proof,provision:true,displayName:activeIdentity?.label||'Membre Quantic'};
      const data=await api(path,{method:'POST',body:JSON.stringify(body)});
      applySession(data);
      await ensureSecureDevice().catch(()=>{});
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
      if(state.feed==='news')loadNewsRss();
      else loadHome();
    });
  });

  document.querySelectorAll('[data-view]').forEach(function(button){
    button.addEventListener('click',function(){
      const view=button.dataset.view;
      if(view==='home'){
        state.feed='following';
        document.querySelectorAll('.pulse-tab').forEach(tab=>tab.classList.toggle('active',tab.dataset.feed==='following'));
        loadHome();
      }
      else if(view==='explore')loadExplore(document.getElementById('pulse-search').value);
      else if(view==='visual')loadVisual();
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
    const shortcut=event.target.closest('.pulse-right [data-view],#circle-preview [data-view]');
    if(shortcut){
      const view=shortcut.dataset.view;
      if(view==='messages')void loadMessages();
      else if(view==='circles')void loadCircles();
      else if(view==='visual')void loadVisual();
      else if(view==='explore')void loadExplore(document.getElementById('pulse-search').value);
      return;
    }
    const newsRepost=event.target.closest('[data-news-repost]');
    if(newsRepost){
      if(!requireAuth())return;
      const title=String(newsRepost.dataset.newsTitle||'Actualité').trim();
      const url=safeHttpsUrl(newsRepost.dataset.newsUrl);
      const image=safeHttpsUrl(newsRepost.dataset.newsImage);
      const source=String(newsRepost.dataset.newsSource||'Quantic News').trim();
      const body=(title+(source?'\n\nSource : '+source:'')).slice(0,420);
      const oldLabel=newsRepost.textContent;
      newsRepost.disabled=true;
      newsRepost.textContent='Repost…';
      try{
        await api('/api/pulse/posts',{method:'POST',body:JSON.stringify({body,linkUrl:url,linkTitle:title,imageUrl:image})});
        newsRepost.textContent='Reposté ✓';
        newsRepost.classList.add('done');
      }catch(error){
        newsRepost.disabled=false;
        newsRepost.textContent=oldLabel;
        alert(errorText(error));
      }
      return;
    }

    const profile=event.target.closest('[data-profile]');
    if(profile){
      loadProfile(profile.dataset.profile);
      return;
    }

    const visual=event.target.closest('[data-visual-post]');
    if(visual){
      void (async()=>{
        try{
          const result=await api('/api/pulse/posts/'+encodeURIComponent(visual.dataset.visualPost));
          const {renderPost}=await import('./render.js?v=25');
          setView('visual','Publication');
          dom.feed.innerHTML=renderPost(result.post);
        }catch(error){alert(errorText(error))}
      })();
      return;
    }
    const post=event.target.closest('.pulse-post');
    const action=event.target.closest('[data-action]');
    if(post&&action){
      const postId=post.dataset.id;
      if(action.dataset.action==='delete'){
        void deleteOwnPost(postId,post);
        return;
      }
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
        if(navigator.share)navigator.share({title:'SOCIAL',url:shareUrl}).catch(function(){});
        else navigator.clipboard?.writeText(shareUrl);
        return;
      }
      if(action.dataset.action==='report'){
        reportPost(postId);
        return;
      }
    }

    const openCircle=event.target.closest('[data-circle-open]');
    if(openCircle){void loadCircle(openCircle.dataset.circleOpen);return}
    if(event.target.closest('[data-circle-back]')){void loadCircles();return}
    if(event.target.closest('[data-chat-back]')){void loadMessages();return}
    const openChat=event.target.closest('[data-new-chat]');
    if(openChat){const form=document.getElementById('social-new-chat');if(form){form.hidden=!form.hidden;form.querySelector('input')?.focus()}return}
    const join=event.target.closest('[data-circle-join]');
    if(join){
      if(!requireAuth())return;
      try{
        await api('/api/pulse/circles/'+encodeURIComponent(join.dataset.circleJoin)+'/join',{method:'POST',body:'{}'});
        if(state.activeCircleId===join.dataset.circleJoin)await loadCircle(join.dataset.circleJoin);
        else await loadCircles();
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
    if(event.target.closest('[data-profile-avatar]')){void uploadOwnAvatar();return}
    if(event.target.closest('[data-logout]')){doLogout();return}
  });

  document.addEventListener('input',function(event){
    if(event.target.id==='social-chat-search'){
      const query=event.target.value.trim().toLowerCase();
      document.querySelectorAll('#social-inbox-list [data-chat-label]').forEach(item=>{
        item.hidden=!item.dataset.chatLabel.includes(query);
      });
    }
  });
  document.addEventListener('submit',async function(event){
    if(event.target.id==='social-new-chat'){
      event.preventDefault();
      const handle=String(new FormData(event.target).get('handle')||'').trim().replace(/^@/,'');
      if(!/^[a-z0-9_]{3,24}$/i.test(handle)){alert('Identifiant SOCIAL invalide.');return}
      void loadConversation(handle.toLowerCase());
      return;
    }
    if(event.target.id==='circle-publish'){
      event.preventDefault();
      if(!requireAuth())return;
      const form=event.target,body=String(new FormData(form).get('body')||'').trim(),circleId=form.dataset.circleId;
      const max=Number(state.user?.maxPostLength||420);
      if(!body||Array.from(body).length>max){alert('Votre publication doit contenir entre 1 et '+max+' caractères.');return}
      const button=form.querySelector('button[type=submit]');
      if(button)button.disabled=true;
      try{
        await api('/api/pulse/posts',{method:'POST',body:JSON.stringify({body,circleId})});
        await loadCircle(circleId);
      }catch(error){alert(errorText(error));if(button)button.disabled=false}
      return;
    }
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
        const handle=String(form.get('handle')||'').replace(/^@/,'');
        await sendSecureMessage(handle,String(form.get('body')||''));
        await loadMessages();
      }catch(error){alert(errorText(error))}
    }

    if(event.target.id==='conversation-form'){
      event.preventDefault();
      const form=new FormData(event.target);
      const handle=event.target.dataset.handle;
      try{
        await sendSecureMessage(handle,String(form.get('body')||''));
        await loadConversation(handle);
      }catch(error){alert(errorText(error))}
    }
  });
}

function applyIncomingShare(){
  const params=new URLSearchParams(location.search);
  if(params.get('share')!=='news')return;
  const title=(params.get('title')||'').trim();
  const url=(params.get('url')||'').trim();
  const image=(params.get('image')||'').trim();
  const parts=[];
  if(title)parts.push(title);
  if(url)parts.push(url);
  const draft=parts.join('\n\n').slice(0,420);
  if(image||url)state.attachment={linkUrl:safeHttpsUrl(url),linkTitle:title,imageUrl:safeHttpsUrl(image)};
  updateMediaPreview();
  if(draft){
    dom.textarea.value=draft;
    dom.count.textContent=dom.textarea.value.length+' / 420';
    dom.publish.disabled=!dom.textarea.value.trim();
    setView('home','Accueil');
    setTimeout(()=>dom.textarea.focus(),0);
  }
  history.replaceState({},document.title,location.pathname);
}

async function init(){
  bindStaticEvents();
  applyIncomingShare();
  bindDelegatedEvents();
  await health();
  await restoreSession();
  if(state.user)await ensureSecureDevice().catch(()=>{});
  startIdentityPresenceGuard();
  await Promise.all([loadHome(),loadCirclePreview()]);
  const reconnect=async()=>{
    if(document.visibilityState==='hidden'||state.user||state.identityStatus==='checking')return;
    if(await retryIdentityConnection())await Promise.all([loadHome(),loadCirclePreview()]);
  };
  setInterval(reconnect,60000);
  window.addEventListener('pageshow',reconnect);
  document.addEventListener('visibilitychange',reconnect);
}

init();
