(()=>{
  'use strict';
  document.documentElement.classList.add('providence-v11');
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const canvas=document.createElement('canvas');canvas.className='providence-atmosphere';canvas.setAttribute('aria-hidden','true');document.body.prepend(canvas);
  const ctx=canvas.getContext('2d',{alpha:true});let w=0,h=0,dpr=1,points=[],mouse={x:.5,y:.35};
  function resize(){dpr=Math.min(devicePixelRatio||1,2);w=innerWidth;h=innerHeight;canvas.width=w*dpr;canvas.height=h*dpr;canvas.style.width=`${w}px`;canvas.style.height=`${h}px`;ctx.setTransform(dpr,0,0,dpr,0,0);const n=Math.max(36,Math.min(110,Math.floor(w*h/18000)));points=Array.from({length:n},()=>({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-.5)*.08,vy:(Math.random()-.5)*.08,r:.5+Math.random()*1.3,p:Math.random()*Math.PI*2}));}
  addEventListener('resize',resize,{passive:true});addEventListener('pointermove',e=>{mouse.x=e.clientX/w;mouse.y=e.clientY/h},{passive:true});resize();
  function frame(t){ctx.clearRect(0,0,w,h);const glow=ctx.createRadialGradient(w*(.55+(mouse.x-.5)*.08),h*(.18+(mouse.y-.5)*.04),0,w*.52,h*.2,Math.max(w,h)*.65);glow.addColorStop(0,'rgba(61,162,255,.055)');glow.addColorStop(.5,'rgba(102,75,210,.025)');glow.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
    for(const p of points){p.x+=p.vx;p.y+=p.vy;if(p.x<-5)p.x=w+5;if(p.x>w+5)p.x=-5;if(p.y<-5)p.y=h+5;if(p.y>h+5)p.y=-5;const pulse=.45+.35*Math.sin(t*.00045+p.p);ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle=`rgba(126,211,255,${.12*pulse})`;ctx.fill();}
    ctx.lineWidth=.5;for(let i=0;i<points.length;i++){for(let j=i+1;j<Math.min(points.length,i+12);j++){const a=points[i],b=points[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.hypot(dx,dy);if(d<125){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=`rgba(94,181,255,${(1-d/125)*.035})`;ctx.stroke();}}}
    requestAnimationFrame(frame);
  }requestAnimationFrame(frame);
})();