const $=(selector)=>document.querySelector(selector);
const statusBox=$("#status");
const createForm=$("#create-form");
const unlockForm=$("#unlock-form");
const modeText=$("#mode");
const locationText=$("#location");
const lockButton=$("#lock");
const revealButton=$("#reveal");
const portablePass=$("#portable-pass-wrap");
const portableUnlock=$("#portable-unlock-wrap");

function humanError(error){
  const code=String(error?.message||error||"");
  const map={
    portable_passphrase_too_short:"Le code local doit contenir au moins 8 caractères.",
    system_encryption_unavailable:"Le chiffrement système Windows n’est pas disponible.",
    vault_not_found:"Aucun coffre n’existe encore.",
    UnsupportedState:"Le coffre ne peut pas être déchiffré sur ce compte Windows."
  };
  return map[code]||code;
}

function render(status){
  modeText.textContent=status.vaultMode==="portable"?"Mode portable · clé USB":"Mode PC · chiffrement Windows";
  locationText.textContent=status.vaultPath||"";
  document.body.dataset.mode=status.vaultMode;
  portablePass.hidden=status.vaultMode!=="portable";
  portableUnlock.hidden=status.vaultMode!=="portable";

  if(status.identityAvailable){
    statusBox.dataset.state="ready";
    statusBox.innerHTML="<strong>Quantic ID actif</strong><span>"+escapeHtml(status.label||status.keyId)+"</span><small>"+escapeHtml(status.keyId||"")+"</small>";
    createForm.hidden=true;
    unlockForm.hidden=true;
    lockButton.hidden=false;
  }else if(status.vaultExists){
    statusBox.dataset.state="locked";
    statusBox.innerHTML="<strong>Identity Vault verrouillé</strong><span>Déverrouillez le coffre pour activer Quantic ID.</span>";
    createForm.hidden=true;
    unlockForm.hidden=false;
    lockButton.hidden=true;
  }else{
    statusBox.dataset.state="empty";
    statusBox.innerHTML="<strong>Aucune identité</strong><span>Créez votre Quantic ID sur cet appareil.</span>";
    createForm.hidden=false;
    unlockForm.hidden=true;
    lockButton.hidden=true;
  }
}

function escapeHtml(value){
  return String(value||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c]));
}

async function refresh(){
  try{render(await window.IdentityVault.status())}
  catch(error){statusBox.innerHTML="<strong>Erreur</strong><span>"+escapeHtml(humanError(error))+"</span>"}
}

createForm.addEventListener("submit",async event=>{
  event.preventDefault();
  const data=new FormData(createForm);
  try{
    const result=await window.IdentityVault.create({label:data.get("label"),passphrase:data.get("passphrase")});
    render(result);
    createForm.reset();
  }catch(error){alert(humanError(error))}
});

unlockForm.addEventListener("submit",async event=>{
  event.preventDefault();
  const data=new FormData(unlockForm);
  try{
    const result=await window.IdentityVault.unlock(data.get("passphrase")||"");
    render(result);
    unlockForm.reset();
  }catch(error){alert(humanError(error))}
});

lockButton.addEventListener("click",async()=>render(await window.IdentityVault.lock()));
revealButton.addEventListener("click",()=>window.IdentityVault.revealLocation());

refresh();
setInterval(refresh,5000);
