(()=>{
  'use strict';
  const root=document.documentElement;
  root.classList.add('providence-v11','providence-v12');
  const css=[
    '/providence-v12.css?v=providence-v12-1',
    '/providence-v12-responsive.css?v=providence-v12-1',
    '/providence-v12-1.css?v=providence-v12-1'
  ];
  for(const href of css){if(!document.querySelector(`link[href^="${href.split('?')[0]}"]`)){const link=document.createElement('link');link.rel='stylesheet';link.href=href;document.head.appendChild(link);}}

  const path=location.pathname.replace(/\/+$/,'')||'/';
  const rawPage=document.body.dataset.page||'';
  const infer=()=>{if(path==='/')return'home';for(const k of ['predictions','horizons','causal','sports','intelligence','track-record','modules','sources','cameras'])if(path.includes(`/${k}`))return k;return rawPage||'home';};
  const page=infer();
  document.body.dataset.pv12Theme=page;
  document.body.classList.add('pv12-command-center');

  const nav=[
    ['home','/','⌾','Vue d’ensemble'],
    ['predictions','/predictions/','◈','Prédictions'],
    ['horizons','/horizons/','◷','Horizons'],
    ['causal','/causal/','⌘','Causal World'],
    ['sports','/sports/','⚽','Sports Calibration'],
    ['intelligence','/intelligence/','◆','Décision Intelligence'],
    ['track-record','/track-record/','▥','Track Record'],
    ['modules','/modules/','⬡','Modules & Modèles'],
    ['sources','/sources/','≋','Sources & Données'],
    ['cameras','/cameras/','◉','Monde en direct']
  ];
  const navLinks=compact=>nav.map(([key,href,icon,label])=>`<a href="${href}" class="${key===page?'active':''}" ${key===page?'aria-current="page"':''}>${compact?'':`<span class="pv12-side-icon">${icon}</span>`}<span>${label}</span></a>`).join('');

  /* Remove the architectural bug: every page gets the exact same navigation source. */
  for(const topNav of document.querySelectorAll('.v4-nav,.topbar nav')){
    topNav.innerHTML=navLinks(true);
    topNav.setAttribute('aria-label','Navigation Providence');
  }

  if(!document.querySelector('.pv12-sidebar')){
    const aside=document.createElement('aside');
    aside.className='pv12-sidebar';
    aside.setAttribute('aria-label','Navigation Providence');
    aside.innerHTML=`<a class="pv12-side-brand" href="/"><span class="pv12-side-mark"></span><span><strong>PROVIDENCE</strong><small>VOIR · CALIBRER · COMPRENDRE</small></span></a><nav class="pv12-side-nav">${navLinks(false)}</nav><div class="pv12-mission"><div class="pv12-mission-orb">◉</div><strong>NOTRE MISSION</strong><p>Mesurer la réalité.<br>Améliorer la prédiction.<br>Réduire l’incertitude.</p></div><div class="pv12-side-foot">PROVIDENCE V12.1 · Unified Command Center</div>`;
    document.body.prepend(aside);
  }

  if(!document.querySelector('.pv12-scene')){
    const scene=document.createElement('div');
    scene.className='pv12-scene';
    scene.setAttribute('aria-hidden','true');
    scene.innerHTML='<div class="globe"></div><div class="orbit"></div><div class="horizon"></div><div class="scan"></div>';
    document.body.prepend(scene);
  }

  const topbar=document.querySelector('.v4-topbar');
  if(topbar&&!topbar.querySelector('.pv12-profile')){
    const profile=document.createElement('div');
    profile.className='pv12-profile';
    profile.innerHTML='<span class="avatar">P</span><span><strong>Providence Live</strong><small>V12.1 · Unified Shell</small></span>';
    const live=topbar.querySelector('.v4-live');
    if(live)topbar.insertBefore(profile,live);else topbar.append(profile);
  }
  const brandStrong=document.querySelector('.v4-brand strong,.topbar .brand strong');if(brandStrong)brandStrong.textContent='PROVIDENCE';
  const themeMeta=document.querySelector('meta[name="theme-color"]');if(themeMeta)themeMeta.content='#02060d';

  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const canvas=document.createElement('canvas');
  canvas.className='providence-atmosphere';
  canvas.setAttribute('aria-hidden','true');
  document.body.prepend(canvas);
  const ctx=canvas.getContext('2d',{alpha:true});
  let w=0,h=0,dpr=1,points=[],mouse={x:.5,y:.35};
  const palette={home:[70,184,255],predictions:[140,104,255],horizons:[63,220,255],causal:[181,92,255],sports:[52,180,255],intelligence:[66,226,210],'track-record':[62,175,255],modules:[65,215,255],sources:[82,231,186],cameras:[56,200,255]};
  const secondary={home:[112,92,255],predictions:[222,91,255],horizons:[255,196,79],causal:[255,84,194],sports:[92,239,136],intelligence:[255,202,82],'track-record':[82,239,173],modules:[255,95,202],sources:[255,204,77],cameras:[97,104,255]};
  const rgb=palette[page]||palette.home, rgb2=secondary[page]||secondary.home;
  function resize(){dpr=Math.min(devicePixelRatio||1,2);w=innerWidth;h=innerHeight;canvas.width=w*dpr;canvas.height=h*dpr;canvas.style.width=`${w}px`;canvas.style.height=`${h}px`;ctx.setTransform(dpr,0,0,dpr,0,0);const n=Math.max(44,Math.min(128,Math.floor(w*h/15000)));points=Array.from({length:n},()=>({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-.5)*.1,vy:(Math.random()-.5)*.1,r:.45+Math.random()*1.5,p:Math.random()*Math.PI*2}));}
  addEventListener('resize',resize,{passive:true});
  addEventListener('pointermove',e=>{mouse.x=e.clientX/Math.max(w,1);mouse.y=e.clientY/Math.max(h,1)},{passive:true});
  resize();
  function frame(t){
    ctx.clearRect(0,0,w,h);
    let glow=ctx.createRadialGradient(w*(.58+(mouse.x-.5)*.08),h*(.14+(mouse.y-.5)*.05),0,w*.55,h*.18,Math.max(w,h)*.72);
    glow.addColorStop(0,`rgba(${rgb.join(',')},.095)`);glow.addColorStop(.42,`rgba(${rgb2.join(',')},.035)`);glow.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
    const glow2=ctx.createRadialGradient(w*.84,h*.58,0,w*.84,h*.58,Math.max(w,h)*.35);glow2.addColorStop(0,`rgba(${rgb2.join(',')},.026)`);glow2.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=glow2;ctx.fillRect(0,0,w,h);
    for(const p of points){p.x+=p.vx;p.y+=p.vy;if(p.x<-5)p.x=w+5;if(p.x>w+5)p.x=-5;if(p.y<-5)p.y=h+5;if(p.y>h+5)p.y=-5;const pulse=.45+.35*Math.sin(t*.00045+p.p);ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle=`rgba(${rgb.join(',')},${.16*pulse})`;ctx.fill();}
    ctx.lineWidth=.55;
    for(let i=0;i<points.length;i++){for(let j=i+1;j<Math.min(points.length,i+13);j++){const a=points[i],b=points[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.hypot(dx,dy);if(d<132){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=`rgba(${rgb.join(',')},${(1-d/132)*.045})`;ctx.stroke();}}}
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();