(()=>{'use strict';const form=document.getElementById('qs-contact-form');if(!form)return;
const choices={pro:"Je souhaite discuter de l'offre Pro et de la mise en service.",business:"Je souhaite discuter de l'offre Business et du déploiement de mon équipe.",enterprise:"Je souhaite étudier une offre Enterprise personnalisée.",projet:"Je souhaite présenter un projet à Quantic Sillage.",proposition:"Je souhaite recevoir une proposition commerciale."};
const selected=new URLSearchParams(window.location.search).get('offre');
if(selected&&Object.prototype.hasOwnProperty.call(choices,selected)){const field=document.getElementById('qs-message');if(field&&!field.value)field.value=choices[selected]+'\n\nNos besoins : ';}
form.addEventListener('submit',event=>{event.preventDefault();if(!form.reportValidity())return;
const val=id=>document.getElementById(id)?.value?.trim()||'';
const subject='Quantic Sillage — projet de '+val('qs-company');
const body=['Bonjour,','','Je souhaite discuter d’un projet avec Quantic Sillage.','','Nom : '+val('qs-name'),'Organisation : '+val('qs-company'),'E-mail : '+val('qs-email'),"Taille de l’équipe : "+val('qs-size'),'','Description du projet :',val('qs-message'),'','Merci.'].join('\n');
window.location.href='mailto:contact@quanticminds.fr?subject='+encodeURIComponent(subject)+'&body='+encodeURIComponent(body);
});})();