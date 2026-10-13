(()=>{'use strict';const form=document.getElementById('qs-contact-form');if(!form)return;
form.addEventListener('submit',event=>{event.preventDefault();if(!form.reportValidity())return;
const val=id=>document.getElementById(id)?.value?.trim()||'';
const subject='Quantic Sillage — projet de '+val('qs-company');
const body=['Bonjour,','','Je souhaite discuter d’un projet avec Quantic Sillage.','','Nom : '+val('qs-name'),'Organisation : '+val('qs-company'),'E-mail : '+val('qs-email'),"Taille de l’équipe : "+val('qs-size'),'','Description du projet :',val('qs-message'),'','Merci.'].join('\n');
window.location.href='mailto:contact@quanticminds.fr?subject='+encodeURIComponent(subject)+'&body='+encodeURIComponent(body);
});})();