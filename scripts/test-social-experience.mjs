import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=path=>readFileSync(path,'utf8');
const html=read('public/pulse/index.html');
const views=read('public/pulse/views.js');
const app=read('public/pulse/app.js');
const server=read('src/quantic_pulse.js');
const session=read('public/pulse/session.js');
const render=read('public/pulse/render.js');
const styles=read('public/pulse/social-experience.css');
const spark=read('public/pulse/social-spark.css');
const offers=read('public/pulse/offres/index.html');
for(const label of ['Discussions privées','Galerie','Communautés','social-moments','social-photo-input','social-experience.css']){
  assert.ok(html.includes(label),'social layout '+label);
}
assert.ok(!html.includes('Comment ça marche ?'),'tutorial occupies product space');
for(const marker of ['social-messenger','social-chat-room','social-chat-bubble','social-chat-send','socialInboxConversations','socialInboxSidebar','social-community-grid','social-circle-timeline','circle-publish','social-profile-media']){
  assert.ok(views.includes(marker)||styles.includes(marker),'missing functional module '+marker);
}
for(const route of ["'/api/pulse/circles/'+encodeURIComponent(circleId)+'/posts'","'/api/pulse/posts'"]){
  assert.ok(views.includes(route)||app.includes(route),'community post interface '+route);
}
assert.ok(server.includes('posts=Object.values(store.posts).filter(p=>p.circleId===circle.id'),'community API route');
assert.ok(server.includes("circle.visibility!=='public'&&!joined"),'private community authorization');
assert.ok(server.includes('SOCIAL_POST_LIMITS=Object.freeze({free:420,plus:2000,pro:10000})'),'tier length mapping');
assert.ok(server.includes('SOCIAL_MEMBERSHIPS_JSON'),'operator-controlled membership');
assert.ok(server.includes('socialMembership(user)'),'backend tier check');
assert.ok(server.includes('post_too_long'),'backend over-limit rejection');
assert.ok(server.includes('safePostMedia'),'server media verification');
assert.ok(app.includes("canvas.toDataURL('image/webp'"),'real image compression');
assert.ok(app.includes("data-tool=\"photo\""),'photo attachment handler');
assert.ok(app.includes('sendSecureMessage'),'E2E messaging retained');
assert.ok(session.includes('user?.maxPostLength'),'composer quota from backend');
assert.ok(render.includes('user.subscriberBadge'),'premium mark');
assert.ok(render.includes('user.verified'),'identity verification independent');
for(const marker of ['420 caractères','2 000 caractères','10 000 caractères','Badge Plus','Badge Pro','vérification du compte']){
  assert.ok(offers.includes(marker),'premium benefits '+marker);
}
assert.ok(html.includes('data-view="visual"')&&html.includes('data-view="messages"')&&html.includes('data-view="circles"'),'mobile navigation');

assert.ok(html.includes('/pulse/social-spark.css?v=20261014.1'),'luminous SOCIAL stylesheet loaded');
assert.ok(spark.includes('.social-moment-preview'),'photo-based moments styled');
assert.ok(views.includes('class="social-moment-preview"'),'real photo cards in daily moments');
assert.ok(spark.includes('grid-template-columns:minmax(192px,225px)'),'larger central feed');
assert.ok(spark.includes('linear-gradient(105deg,#3989fb,#926ef2)'),'published action still visible');
console.log(JSON.stringify({ok:true,contract:'social-experience-messaging-visual-communities-tiers'}));
