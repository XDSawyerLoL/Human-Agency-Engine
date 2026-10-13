import { state, dom, api, esc, icon, initials, avatarHtml, safeAvatarUrl, timeAgo, setStatus, errorText } from './core.js?v=25';
import { requireAuth } from './session.js?v=25';
import { renderPost, renderPosts, notificationLabel } from './render.js?v=25';
import { decryptConversationMessages, safetyNumber, decentralizedMessagesFor, decentralizedConversationSummaries } from './secure.js?v=25';

export function setView(view,title){
  state.view=view;
  dom.viewTitle.textContent=title||'SOCIAL';
  document.querySelectorAll('[data-view]').forEach(function(button){
    button.classList.toggle('active',button.dataset.view===view);
  });
  dom.feedTabs.hidden=view!=='home';
  const moments=document.getElementById('social-moments');if(moments&&view!=='home')moments.hidden=true;
  dom.composer.hidden=view!=='home'||!state.user;
  dom.welcome.hidden=view!=='home'||!!state.user;
}

const NEWS_FEEDS=[
  'https://raw.githubusercontent.com/XDSawyerLoL/LEFILLIBRE/main/feed.json',
  'https://xdsawyerlol.github.io/LEFILLIBRE/feed.json'
];

function safeNewsUrl(value){
  try{const url=new URL(String(value||''));return url.protocol==='https:'?url.href:''}catch{return''}
}

function newsTime(iso){
  const t=Date.parse(String(iso||''));if(!Number.isFinite(t))return'';
  const mins=Math.max(0,Math.floor((Date.now()-t)/60000));
  if(mins<60)return mins+' min';
  const hours=Math.floor(mins/60);if(hours<24)return hours+' h';
  return new Date(t).toLocaleDateString('fr-FR',{day:'2-digit',month:'short'});
}

async function fetchNewsFeed(){
  let lastError;
  for(const endpoint of NEWS_FEEDS){
    try{
      const response=await fetch(endpoint+(endpoint.includes('?')?'&':'?')+'v='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const data=await response.json();
      if(!Array.isArray(data.items))throw new Error('invalid_news_feed');
      return data;
    }catch(error){lastError=error}
  }
  throw lastError||new Error('news_feed_unavailable');
}

function renderNewsCard(item){
  const title=String(item.title||'Actualité');
  const source=String(item.source||'Quantic News');
  const url=safeNewsUrl(item.url||item.articleUrl);
  const image=safeNewsUrl(item.image);
  const summary=String(item.summary||'').slice(0,280);
  return '<article class="pulse-news-card">'+
    (image?'<a class="pulse-news-media" href="'+esc(url||image)+'" target="_blank" rel="noopener noreferrer"><img src="'+esc(image)+'" alt="" loading="lazy" referrerpolicy="no-referrer"></a>':'')+
    '<div class="pulse-news-body"><div class="pulse-news-meta"><span>RSS</span><strong>'+esc(source)+'</strong><span>'+esc(newsTime(item.publishedAt))+'</span></div>'+
    '<h2>'+esc(title)+'</h2>'+
    (summary?'<p>'+esc(summary)+(String(item.summary||'').length>280?'…':'')+'</p>':'')+
    '<div class="pulse-news-actions">'+
      (url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Lire la source ↗</a>':'')+
      '<button type="button" data-news-repost data-news-title="'+esc(title)+'" data-news-source="'+esc(source)+'" data-news-url="'+esc(url)+'" data-news-image="'+esc(image)+'">Reposter sur SOCIAL</button>'+
    '</div></div></article>';
}

export async function loadNewsRss(){
  state.feed='news';
  setView('home','Quantic News');
  dom.composer.hidden=true;
  setStatus('Connexion à Quantic News','Lecture du flux RSS…');
  try{
    const data=await fetchNewsFeed();
    const items=(data.items||[]).filter(item=>item&&item.title).sort((a,b)=>Date.parse(b.publishedAt||0)-Date.parse(a.publishedAt||0)).slice(0,50);
    dom.feed.innerHTML=items.length
      ? '<section class="pulse-news-view"><div class="pulse-news-intro"><span>QUANTIC NEWS · RSS</span><h2>Actualités à lire et à reposter</h2><p>Le flux Quantic News est intégré à SOCIAL. Un repost crée une publication SOCIAL avec le titre, la source, le lien et l’image de l’article.</p></div><div class="pulse-news-grid">'+items.map(renderNewsCard).join('')+'</div></section>'
      : '<div class="pulse-status"><strong>Flux vide</strong>Aucune actualité disponible pour le moment.</div>';
  }catch(error){
    setStatus('Quantic News indisponible','Impossible de lire le flux RSS pour le moment.');
  }
}

export async function loadHome(){
  if(state.feed==='news')return loadNewsRss();
  setView('home','Accueil');
  setStatus('Chargement du fil','');
  try{
    const [feed,visual]=await Promise.all([
      api('/api/pulse/feed?mode='+state.feed+'&limit=40'),
      api('/api/pulse/feed?mode=discover&limit=50').catch(()=>({posts:[]}))
    ]);
    renderPosts(feed.posts,state.user&&state.feed==='following'?'Suivez des comptes ou publiez dans votre fil.':'Aucune publication publique.');
    const moments=document.getElementById('social-moments');
    if(moments){
      const seen=new Set();
      const stories=(visual.posts||[]).filter(post=>{
        const key=post.author?.id||post.author?.handle;
        if(!key||seen.has(key)||!safeAvatarUrl(post.mediaUrl||post.imageUrl))return false;
        seen.add(key);return true;
      }).slice(0,9);
      if(stories.length){
        moments.innerHTML='<div class="social-moments-head"><strong>Moments du jour</strong><button type="button" data-view="visual">Tout voir →</button></div><div class="social-moments-list">'+stories.map(post=>
          '<button type="button" class="social-moment" data-visual-post="'+esc(post.id)+'" aria-label="Voir la publication de '+esc(post.author?.displayName||post.author?.handle||'SOCIAL')+'">'+
          '<span class="social-moment-ring">'+avatarHtml(post.author||{})+'</span><small>'+esc((post.author?.displayName||post.author?.handle||'Membre').slice(0,16))+'</small></button>'
        ).join('')+'</div>';
        moments.hidden=false;
      }else{moments.hidden=true;moments.innerHTML=''}
    }
  }catch(error){setStatus('SOCIAL indisponible',errorText(error))}
}

export async function loadExplore(query=''){
  setView('explore','Explorer');
  if(query.trim().length<2){
    dom.feed.innerHTML='<section class="pulse-view"><div class="pulse-view-head"><h2>Explorer SOCIAL</h2><p>Recherche des personnes, des sujets et des publications.</p></div></section>';
    return;
  }

  setStatus('Recherche','');
  try{
    const data=await api('/api/pulse/search?q='+encodeURIComponent(query.trim()));
    let html='<section class="pulse-view"><div class="pulse-view-head"><h2>Résultats</h2><p>'+esc(query)+'</p></div><div class="pulse-card-list">';
    data.users.forEach(function(user){
      html+='<div class="pulse-card pulse-user-card">'+avatarHtml(user)+'<div><strong>'+esc(user.displayName)+'</strong><small>@'+esc(user.handle)+' · '+user.followers+' abonnés</small></div><button class="pulse-mini-button" data-profile="'+esc(user.handle)+'">Voir</button></div>';
    });
    html+='</div></section>';
    if(data.posts?.length)html+=data.posts.map(renderPost).join('');
    if(!data.users?.length&&!data.posts?.length)html+='<div class="pulse-status"><strong>Aucun résultat</strong>Essaie une autre recherche.</div>';
    dom.feed.innerHTML=html;
  }catch(error){
    setStatus('Recherche impossible',errorText(error));
  }
}

export async function loadVisual(){
  setView('visual','Galerie');
  setStatus('Chargement des images','Découvrir les publications illustrées de SOCIAL.');
  try{
    const data=await api('/api/pulse/feed?mode=discover&limit=50');
    const posts=(data.posts||[]).filter(post=>post.mediaUrl||post.imageUrl);
    if(!posts.length){
      setStatus('La galerie prend forme','Aucune publication illustrée récente. Ajoutez un GIF ou une image depuis les fonctions disponibles dans SOCIAL.');
      return;
    }
    dom.feed.innerHTML='<section class="pulse-view pulse-visual-view"><div class="pulse-view-head"><h2>Galerie SOCIAL</h2><p>Les images partagées publiquement au cours des dernières 24 heures.</p></div><div class="pulse-visual-grid">'+posts.map(post=>{
      const raw=post.mediaUrl||post.imageUrl;
      const url=safeAvatarUrl(raw);
      if(!url)return '';
      return '<button type="button" class="pulse-visual-tile" data-visual-post="'+esc(post.id)+'" aria-label="Ouvrir la publication illustrée de @'+esc(post.author?.handle||'social')+'"><img src="'+esc(url)+'" loading="lazy" alt="'+esc(post.body||'Publication illustrée')+'" referrerpolicy="no-referrer"><div><strong>@'+esc(post.author?.handle||'social')+'</strong><span>'+esc((post.body||'').slice(0,95))+'</span></div></button>';
    }).join('')+'</div></section>';
  }catch(error){setStatus('Galerie indisponible',errorText(error))}
}

export async function loadCircles(){
  state.activeCircleId=null;
  setView('circles','Communautés');
  setStatus('Chargement des communautés','');
  try{
    const {circles=[]}=await api('/api/pulse/circles');
    const mine=circles.filter(circle=>circle.joined);
    const discover=circles.filter(circle=>!circle.joined);
    const renderCircle=circle=>'<article class="social-community-card">'+
      '<button class="social-community-cover" data-circle-open="'+esc(circle.id)+'" aria-label="Ouvrir '+esc(circle.name)+'"><span>'+esc(circle.name.slice(0,2).toUpperCase())+'</span></button>'+
      '<div class="social-community-details"><h3><button data-circle-open="'+esc(circle.id)+'">'+esc(circle.name)+'</button></h3>'+
      '<p>'+esc(circle.description||'Échangez avec les membres autour de ce sujet.')+'</p>'+
      '<small>'+Number(circle.memberCount||0)+' membre(s) · '+(circle.visibility==='private'?'Espace privé':'Espace public')+'</small>'+
      '<div class="social-community-actions"><button class="pulse-mini-button primary" data-circle-open="'+esc(circle.id)+'">Voir les publications →</button>'+
      (circle.ownerId===state.user?.id?'<span class="social-community-owner">Administrateur</span>':'<button class="pulse-mini-button" data-circle-join="'+esc(circle.id)+'">'+(circle.joined?'Quitter':'Rejoindre')+'</button>')+'</div></div></article>';
    let html='<section class="pulse-view social-community-hub"><header class="social-community-hero"><span class="social-small-label">SOCIAL · LES COMMUNAUTÉS</span><h2>Des espaces où l’on échange vraiment.</h2><p>Rejoignez des groupes, partagez des publications dans leur fil et retrouvez les discussions du même sujet au même endroit.</p></header>';
    if(state.user)html+='<details class="social-create-community"><summary>+ Créer une communauté</summary><form class="social-community-form" id="circle-create"><label>Nom de la communauté<input name="name" minlength="3" maxlength="60" required placeholder="Ex. Cinéma & séries"></label><label>Description<input name="description" maxlength="240" placeholder="De quoi parle-t-on ?"></label><button class="pulse-mini-button primary" type="submit">Créer cet espace</button></form></details>';
    if(mine.length)html+='<div class="social-community-section"><h3>Mes communautés <span>'+mine.length+'</span></h3><div class="social-community-grid">'+mine.map(renderCircle).join('')+'</div></div>';
    html+='<div class="social-community-section"><h3>À découvrir <span>'+discover.length+'</span></h3><div class="social-community-grid">'+(discover.length?discover.map(renderCircle).join(''):'<div class="social-empty-community">Aucune nouvelle communauté à découvrir. Vous pouvez créer la première.</div>')+'</div></div></section>';
    dom.feed.innerHTML=html;
  }catch(error){setStatus('Communautés indisponibles',errorText(error))}
}

export async function loadCircle(circleId){
  state.activeCircleId=circleId;
  setView('circles','Communauté');
  setStatus('Chargement du groupe','');
  try{
    const {circle,posts=[]}=await api('/api/pulse/circles/'+encodeURIComponent(circleId)+'/posts');
    const canPublish=Boolean(state.user&&circle.joined);
    const maxLength=state.user?.maxPostLength||420;
    dom.feed.innerHTML='<section class="pulse-view social-circle-timeline">'+
      '<button class="social-back-link" data-circle-back>← Toutes les communautés</button>'+
      '<header class="social-circle-header"><div class="social-circle-cover">'+esc(circle.name.slice(0,2).toUpperCase())+'</div><div><span class="social-small-label">COMMUNAUTÉ · '+(circle.visibility==='private'?'PRIVÉE':'PUBLIQUE')+'</span><h2>'+esc(circle.name)+'</h2><p>'+esc(circle.description||'Un espace pour échanger avec la communauté.')+'</p><small>'+Number(circle.memberCount||0)+' membres</small></div></header>'+
      (canPublish?'<form id="circle-publish" data-circle-id="'+esc(circle.id)+'" class="social-community-publish"><label for="social-circle-text">Publier dans '+esc(circle.name)+'</label><textarea id="social-circle-text" name="body" maxlength="'+maxLength+'" required placeholder="Une idée, une question, une discussion…"></textarea><div><span>'+maxLength+' caractères maximum</span><button class="pulse-mini-button primary" type="submit">Publier dans la communauté</button></div></form>':'<div class="social-join-callout">Rejoignez cette communauté pour y publier. <button class="pulse-mini-button primary" data-circle-join="'+esc(circle.id)+'">Rejoindre</button></div>')+
      '<div class="social-community-section"><h3>Fil de la communauté <span>'+posts.length+'</span></h3></div>'+
      (posts.length?posts.map(renderPost).join(''):'<div class="social-empty-community">Aucune publication pour le moment. Ouvrez la conversation.</div>')+'</section>';
  }catch(error){setStatus('Communauté indisponible',errorText(error))}
}

export async function loadNotifications(){
  if(!requireAuth())return;
  setView('notifications','Notifications');
  setStatus('Chargement','');
  try{
    const data=await api('/api/pulse/notifications');
    let html='<section class="pulse-view"><div class="pulse-view-head"><h2>Notifications</h2><p>Les interactions importantes, sans fabriquer une boucle d’attention.</p></div><div class="pulse-card-list">';
    if(!data.notifications.length)html+='<div class="pulse-card"><p>Aucune notification.</p></div>';
    data.notifications.forEach(function(notification){
      const actor=notification.actor||{};
      html+='<div class="pulse-card pulse-notification '+(notification.read?'':'unread')+'"><strong>'+esc(actor.displayName||'Quelqu’un')+'</strong> '+esc(notificationLabel(notification.type))+'<div class="pulse-card-meta">'+esc(timeAgo(notification.createdAt))+'</div></div>';
    });
    dom.feed.innerHTML=html+'</div></section>';
    await api('/api/pulse/notifications/read',{method:'POST',body:'{}'});
  }catch(error){
    setStatus('Notifications indisponibles',errorText(error));
  }
}

export async function loadSaved(){
  if(!requireAuth())return;
  setView('saved','Enregistrés');
  setStatus('Chargement','');
  try{
    const data=await api('/api/pulse/me/bookmarks');
    renderPosts(data.posts,'Tu n’as encore enregistré aucune publication.');
  }catch(error){
    setStatus('Enregistrés indisponibles',errorText(error));
  }
}

export async function loadProfile(handle){
  if(!handle){
    if(!requireAuth())return;
    handle=state.user.handle;
  }
  setView('profile','Profil');
  setStatus('Chargement du profil','');
  try{
    const data=await api('/api/pulse/users/'+encodeURIComponent(handle));
    const user=data.user;
    const self=state.user&&state.user.id===user.id;
    let actions='';

    if(self){
      actions='<button class="pulse-mini-button primary" data-profile-edit>Modifier</button><button class="pulse-mini-button" data-profile-avatar>Changer la photo</button><button class="pulse-mini-button" data-export>Exporter mes données</button><button class="pulse-mini-button danger" data-logout>Déconnexion</button>';
    }else if(state.user){
      actions='<button class="pulse-mini-button primary" data-follow="'+esc(user.handle)+'">'+(user.isFollowing?'Se désabonner':'Suivre')+'</button><button class="pulse-mini-button" data-message-user="'+esc(user.handle)+'">Message</button><button class="pulse-mini-button danger" data-block="'+esc(user.handle)+'">Bloquer</button>';
    }

    dom.feed.innerHTML='<section class="pulse-profile-hero">'+avatarHtml(user)+'<h2>'+esc(user.displayName)+'</h2><div class="handle">@'+esc(user.handle)+'</div><p>'+esc(user.bio||'Aucune bio pour le moment.')+'</p><div class="pulse-profile-stats"><span><strong>'+user.followers+'</strong> abonnés</span><span><strong>'+user.following+'</strong> abonnements</span></div><div class="pulse-profile-actions">'+actions+'</div></section>'+((data.posts||[]).map(renderPost).join('')||'<div class="pulse-status"><strong>Aucune publication</strong></div>');
  }catch(error){
    setStatus('Profil indisponible',errorText(error));
  }
}

async function socialInboxConversations(){
  let central={conversations:[]};
  try{central=await api('/api/pulse/conversations')}catch{}
  const local=await decentralizedConversationSummaries().catch(()=>[]);
  const conversations=new Map();
  for(const item of central.conversations||[])if(item.user?.handle)conversations.set(item.user.handle,item);
  for(const item of local){
    if(!item.handle||conversations.has(item.handle))continue;
    conversations.set(item.handle,{user:{handle:item.handle,displayName:item.handle},lastMessage:{body:'',createdAt:item.createdAt,encrypted:true}});
  }
  return [...conversations.values()].sort((a,b)=>Date.parse(b.lastMessage?.createdAt||0)-Date.parse(a.lastMessage?.createdAt||0));
}
function socialInboxSidebar(list,activeHandle=''){
  return '<aside class="social-inbox-sidebar" aria-label="Conversations privées">'+
    '<header class="social-inbox-head"><div><span class="social-small-label">SOCIAL · PRIVÉ</span><h2>Discussions</h2></div><button type="button" class="social-compose-chat" data-new-chat aria-label="Nouvelle conversation">✎</button></header>'+
    '<div class="social-inbox-search"><input id="social-chat-search" type="search" placeholder="Rechercher une discussion" aria-label="Rechercher une discussion" autocomplete="off"></div>'+
    '<form id="social-new-chat" class="social-chat-start" hidden><label for="social-recipient">Écrire à</label><div><input id="social-recipient" name="handle" placeholder="@pseudo" maxlength="24" required><button type="submit">Ouvrir →</button></div></form>'+
    '<div class="social-inbox-list" id="social-inbox-list">'+
    (list.length?list.map(item=>{
      const u=item.user||{},preview=item.lastMessage?.encrypted?'Message chiffré':(item.lastMessage?.body||'Ouvrir la conversation');
      return '<button type="button" class="social-chat-contact '+(u.handle===activeHandle?'active':'')+'" data-conversation="'+esc(u.handle||'')+'" data-chat-label="'+esc((u.displayName||u.handle||'').toLowerCase())+'" aria-current="'+(u.handle===activeHandle?'true':'false')+'">'+avatarHtml(u)+
        '<span class="social-chat-summary"><strong>'+esc(u.displayName||u.handle||'')+'</strong><small>'+esc(preview)+'</small></span><span class="social-chat-chevron">›</span></button>';
    }).join(''):'<div class="social-inbox-empty">Aucune discussion. Utilisez le crayon pour contacter un membre.</div>')+
    '</div><div class="social-inbox-foot">🔒 Messages privés chiffrés de bout en bout · Quantic Secure</div></aside>';
}
function socialMessengerShell(list,content,activeHandle=''){
  return '<section class="social-messenger '+(activeHandle?'has-active-chat':'')+'" aria-label="Messagerie SOCIAL">'+socialInboxSidebar(list,activeHandle)+
   '<section class="social-chat-room" aria-label="Fenêtre de conversation">'+content+'</section></section>';
}
export async function loadMessages(){
  if(!requireAuth())return;
  state.currentChat=null;
  setView('messages','Discussions');
  setStatus('Chargement des conversations','');
  try{
    const list=await socialInboxConversations();
    const empty='<div class="social-chat-welcome"><span class="social-chat-emblem">✉</span><h2>Vos conversations, au même endroit.</h2><p>Retrouvez vos échanges privés. Les messages sont chiffrés sur vos appareils, indépendamment du fil public.</p><button type="button" data-new-chat class="pulse-mini-button primary">Nouvelle discussion</button></div>';
    dom.feed.innerHTML=socialMessengerShell(list,empty);
  }catch(error){setStatus('Discussions indisponibles',errorText(error))}
}
export async function loadConversation(handle){
  if(!requireAuth())return;
  state.currentChat=handle;
  setView('messages','Discussions');
  setStatus('Ouverture de la conversation','');
  try{
    const [list,data,localMessages,number]=await Promise.all([
      socialInboxConversations(),
      api('/api/pulse/messages/'+encodeURIComponent(handle)).catch(()=>({user:{handle,displayName:handle},messages:[]})),
      decentralizedMessagesFor(handle).catch(()=>[]),
      safetyNumber(handle).catch(()=>null)
    ]);
    const user=data.user||{handle,displayName:handle};
    const merged=new Map();
    for(const message of [...localMessages,...(data.messages||[])]){
      const key=String(message.clientMessageId||message.id||'')+':'+String(message.senderDeviceId||'');
      const previous=merged.get(key);
      merged.set(key,previous?{...previous,...message,localBody:previous.localBody||message.localBody}:{...message});
    }
    const messages=await decryptConversationMessages([...merged.values()].sort((a,b)=>Date.parse(a.createdAt||0)-Date.parse(b.createdAt||0)));
    let content='<header class="social-chat-header"><button type="button" data-chat-back class="social-chat-back" aria-label="Retour aux discussions">←</button>'+avatarHtml(user)+
      '<div class="social-chat-peer"><strong>'+esc(user.displayName||user.handle)+'</strong><span>@'+esc(user.handle)+' · Conversation privée</span></div>'+
      '<button class="social-chat-profile" type="button" data-profile="'+esc(handle)+'">Voir le profil</button></header>'+
      (number?'<div class="social-chat-security">🔒 Numéro de sécurité : '+esc(number)+'</div>':'<div class="social-chat-security">🔒 Chiffrement de bout en bout · Quantic Secure</div>')+
      '<div class="social-chat-messages" id="social-chat-messages" role="log" aria-live="polite">'+
      (messages.length?messages.map(message=>{
        const body=message.secureInvalid?'Message chiffré invalide':message.secureUnavailable?'Message chiffré indisponible sur cet appareil':(message.plaintext||'');
        const mine=message.senderId===state.user.id;
        return '<div class="social-chat-bubble '+(mine?'mine':'theirs')+'"><div>'+esc(body)+'</div><small>'+esc(timeAgo(message.createdAt))+(message.secure?' · 🔒':'')+'</small></div>';
      }).join(''):'<div class="social-chat-empty">Début de votre conversation avec @'+esc(handle)+'.</div>')+'</div>'+
      '<form class="social-chat-send" id="conversation-form" data-handle="'+esc(handle)+'"><label for="social-chat-body" class="social-visually-hidden">Message privé</label>'+
      '<input name="body" id="social-chat-body" maxlength="2000" autocomplete="off" placeholder="Écrire un message privé…" required>'+
      '<button type="submit" aria-label="Envoyer le message">➤</button></form>';
    dom.feed.innerHTML=socialMessengerShell(list,content,handle);
    const log=document.getElementById('social-chat-messages');if(log)log.scrollTop=log.scrollHeight;
    document.getElementById('social-chat-body')?.focus();
  }catch(error){setStatus('Conversation indisponible',errorText(error))}
}

export async function loadCirclePreview(){
  try{
    const data=await api('/api/pulse/circles');
    const target=document.getElementById('circle-preview');
    target.innerHTML=data.circles.slice(0,3).map(function(circle){
      return '<button class="circle" data-view="circles"><span class="circle-mark">'+esc(circle.name.slice(0,2).toUpperCase())+'</span><span><strong>'+esc(circle.name)+'</strong><small>'+circle.memberCount+' membres</small></span><span class="circle-chevron">'+icon('pi-chevron')+'</span></button>';
    }).join('')||'<div class="pulse-panel-loading">Aucune communauté publique.</div>';
  }catch{
    document.getElementById('circle-preview').innerHTML='<div class="pulse-panel-loading">Indisponible</div>';
  }
}
