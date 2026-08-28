(()=>{'use strict';
// V15 compatibility bridge: legacy pages keep their business logic but use the new visual shell.
if(!document.querySelector('link[href*="providence-v15.css"]')){const l=document.createElement('link');l.rel='stylesheet';l.href='/providence-v15.css?v=15';document.head.appendChild(l)}
if(!document.querySelector('link[href*="providence-v15-compat.css"]')){const l=document.createElement('link');l.rel='stylesheet';l.href='/providence-v15-compat.css?v=15';document.head.appendChild(l)}
if(!document.querySelector('script[src*="providence-v15-shell.js"]')){const s=document.createElement('script');s.src='/providence-v15-shell.js?v=15';s.defer=true;document.head.appendChild(s)}
})();