import { dom, esc, icon, initials, timeAgo, setStatus } from './core.js';

export function renderPost(post){
  const user=post.author||{};
  const liked=post.viewer?.liked;
  const reposted=post.viewer?.reposted;
  const bookmarked=post.viewer?.bookmarked;
  let quote='';

  if(post.quote){
    quote='<div class="pulse-post-link"><div><small>@'+esc(post.quote.author.handle)+'</small><strong>'+esc(post.quote.body)+'</strong></div></div>';
  }

  return '<article class="pulse-post" data-id="'+esc(post.id)+'">'+
    '<div class="pulse-avatar">'+esc(initials(user))+'</div>'+
    '<div class="pulse-post-main">'+
      '<div class="pulse-post-head"><button data-profile="'+esc(user.handle)+'">'+esc(user.displayName||user.handle)+'</button>'+(user.verified?'<span class="pulse-badge" title="Compte vérifié">'+icon('pi-verified')+'</span>':'')+'<span>@'+esc(user.handle)+' · '+esc(timeAgo(post.createdAt))+'</span></div>'+
      '<p>'+esc(post.body)+'</p>'+quote+
      '<div class="pulse-actions">'+
        '<button class="pulse-action" data-action="reply" aria-label="Répondre" title="Répondre">'+icon('pi-reply')+'<span class="pulse-action-name">Répondre</span><span class="pulse-action-count">'+Number(post.counts?.replies||0)+'</span></button>'+
        '<button class="pulse-action '+(reposted?'active':'')+'" data-action="repost" aria-label="Relay" title="Relayer cette publication">'+icon('pi-relay')+'<span class="pulse-action-name">Relayer</span><span class="pulse-action-count">'+Number(post.counts?.reposts||0)+'</span></button>'+
        '<button class="pulse-action '+(liked?'liked':'')+'" data-action="like" aria-label="Pulse" title="Envoyer un Pulse — montrer que cette publication vous plaît">'+icon('pi-pulse','pi-pulse')+'<span class="pulse-action-name">Pulse</span><span class="pulse-action-count">'+Number(post.counts?.likes||0)+'</span></button>'+
        '<button class="pulse-action '+(bookmarked?'active':'')+'" data-action="bookmark" aria-label="Enregistrer" title="Enregistrer">'+icon('pi-bookmark')+'</button>'+
        '<button class="pulse-action" data-action="share" aria-label="Partager" title="Partager">'+icon('pi-share')+'</button>'+
        '<button class="pulse-action danger" data-action="report" aria-label="Signaler" title="Signaler">'+icon('pi-report')+'</button>'+
      '</div>'+
    '</div>'+
  '</article>';
}

export function renderPosts(posts,emptyText='Aucune publication pour le moment.'){
  if(!posts?.length){
    setStatus('Rien ici pour le moment',emptyText);
    return;
  }
  dom.feed.innerHTML=posts.map(renderPost).join('');
}

export function notificationLabel(type){
  return {
    like:'a envoyé un Pulse à ta publication.',
    repost:'a relayé ta publication.',
    reply:'a répondu à ta publication.',
    quote:'a cité ta publication.',
    follow:'s’est abonné à ton profil.',
    message:'t’a envoyé un message.'
  }[type]||'a interagi avec toi.';
}
