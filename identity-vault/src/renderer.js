const $=(selector)=>document.querySelector(selector);
const statusBox=$("#status");
const createForm=$("#create-form");
const createNote=$("#create-note");
const unlockCard=$("#unlock-card");
const unlockButton=$("#unlock");
const profileForm=$("#profile-form");
const modeText=$("#mode");
const locationText=$("#location");
const lockButton=$("#lock");
const revealButton=$("#reveal");
const loadVaultButton=$("#load-vault");
const appVersionText=$("#app-version");
const photoInput=$("#photo-input");
const photoPreview=$("#photo-preview");
const photoPlaceholder=$("#photo-placeholder");
const photoRemove=$("#photo-remove");
let profilePhotoDataUrl="";

function humanError(error){
  const code=String(error?.message||error||"");
  const map={
    system_encryption_unavailable:"Le chiffrement système Windows n’est pas disponible.",
    vault_not_found:"Aucun coffre n’existe encore.",
    vault_format_invalid:"Ce fichier n’est pas un coffre Quantic Identity Vault valide.",
    usb_key_missing:"Le fichier d’accès de la clé USB est absent. Vérifiez que vous avez bien sélectionné le coffre de la bonne clé.",
    usb_key_invalid:"Le fichier d’accès USB est invalide.",
    usb_vault_unlock_failed:"Le coffre et le fichier d’accès USB ne correspondent pas.",
    legacy_vault_requires_code:"Cet ancien coffre a été créé avec le système de code local. Il est conservé, mais la nouvelle version ne demande plus ce code : créez une nouvelle identité USB sans code.",
    pc_unlock_failed:"Ce coffre PC ne peut pas être déchiffré sur ce compte Windows.",
    profile_photo_invalid:"La photo sélectionnée n’est pas dans un format accepté.",
    profile_photo_too_large:"La photo est trop volumineuse. Utilisez une image de moins de 2 Mo.",
    identity_locked:"Déverrouillez d’abord l’identité."
  };
  const known=Object.entries(map).find(([key])=>code.includes(key));
  return known?known[1]:code;
}

function escapeHtml(value){
  return String(value||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c]));
}

function setPhoto(dataUrl=""){
  profilePhotoDataUrl=String(dataUrl||"");
  if(profilePhotoDataUrl){
    photoPreview.src=profilePhotoDataUrl;
    photoPreview.hidden=false;
    photoPlaceholder.hidden=true;
  }else{
    photoPreview.removeAttribute("src");
    photoPreview.hidden=true;
    photoPlaceholder.hidden=false;
  }
}

function profileFromForm(form){
  const data=new FormData(form);
  const fields=["firstName","middleNames","lastName","preferredName","birthDate","birthPlace","nationality","gender","email","phone","addressLine1","addressLine2","postalCode","city","region","country","occupation","organization","website","emergencyContactName","emergencyContactPhone","notes"];
  const profile={photoDataUrl:profilePhotoDataUrl};
  for(const field of fields)profile[field]=String(data.get(field)||"");
  return profile;
}

function setProfileForm(profile={}){
  const fields=["firstName","middleNames","lastName","preferredName","birthDate","birthPlace","nationality","gender","email","phone","addressLine1","addressLine2","postalCode","city","region","country","occupation","organization","website","emergencyContactName","emergencyContactPhone","notes"];
  for(const field of fields){
    const input=profileForm.elements.namedItem(field);
    if(input)input.value=profile?.[field]||"";
  }
  setPhoto(profile?.photoDataUrl||"");
}

function basicProfileFromCreate(){
  const data=new FormData(createForm);
  return {
    firstName:String(data.get("firstName")||""),
    lastName:String(data.get("lastName")||"")
  };
}

function render(status){
  appVersionText.textContent=status.appVersion?"v"+status.appVersion:"";
  modeText.textContent=status.vaultMode==="portable"?"Mode portable · présence USB":"Mode PC · chiffrement Windows";
  locationText.textContent=status.vaultPath||"";
  document.body.dataset.mode=status.vaultMode;

  createForm.hidden=true;
  unlockCard.hidden=true;
  profileForm.hidden=true;
  lockButton.hidden=true;

  if(status.identityAvailable){
    statusBox.dataset.state="ready";
    statusBox.innerHTML="<strong>Quantic ID déverrouillé</strong><span>"+escapeHtml(status.label||status.keyId)+"</span><small>"+escapeHtml(status.keyId||"")+"</small>";
    profileForm.hidden=false;
    lockButton.hidden=false;
    setProfileForm(status.profile||{});
    return;
  }

  if(status.legacyVault){
    statusBox.dataset.state="error";
    statusBox.innerHTML="<strong>Ancien coffre protégé par code</strong><span>Ce coffre ne peut pas être converti sans son ancien code. Il ne sera pas supprimé : la création d’une nouvelle identité en fera d’abord une sauvegarde automatique.</span>";
    createNote.textContent="Un nouveau coffre USB sans code va être créé. L’ancien identity-vault.json sera sauvegardé automatiquement avant remplacement.";
    createForm.hidden=false;
    return;
  }

  if(status.vaultExists&&status.vaultMode==="portable"){
    if(status.usbPresenceAvailable){
      statusBox.dataset.state="locked";
      statusBox.innerHTML="<strong>Identity Vault verrouillé</strong><span>Clé USB détectée. Cliquez simplement sur Déverrouiller.</span>";
      unlockCard.hidden=false;
    }else{
      statusBox.dataset.state="error";
      statusBox.innerHTML="<strong>Clé USB incomplète</strong><span>Le coffre est présent mais son fichier identity-vault.key est absent. Chargez le coffre depuis la bonne clé USB.</span>";
    }
    return;
  }

  if(status.vaultExists){
    statusBox.dataset.state="locked";
    statusBox.innerHTML="<strong>Identity Vault verrouillé</strong><span>Cliquez sur Déverrouiller.</span>";
    unlockCard.hidden=false;
    return;
  }

  statusBox.dataset.state="empty";
  statusBox.innerHTML="<strong>Aucune identité</strong><span>Créez votre Quantic ID. Sur clé USB, aucun code local ne sera demandé.</span>";
  createNote.textContent="Le coffre sera protégé par la présence physique de la clé USB. Aucun code local ne sera créé.";
  createForm.hidden=false;
}

async function refresh(){
  try{render(await window.IdentityVault.status())}
  catch(error){statusBox.innerHTML="<strong>Erreur</strong><span>"+escapeHtml(humanError(error))+"</span>"}
}

loadVaultButton.addEventListener("click",async()=>{
  try{render(await window.IdentityVault.loadFile())}
  catch(error){alert(humanError(error))}
});

createForm.addEventListener("submit",async event=>{
  event.preventDefault();
  const data=new FormData(createForm);
  try{
    const result=await window.IdentityVault.create({
      label:data.get("label"),
      profile:basicProfileFromCreate()
    });
    render(result);
    createForm.reset();
  }catch(error){alert(humanError(error))}
});

unlockButton.addEventListener("click",async()=>{
  try{render(await window.IdentityVault.unlock())}
  catch(error){
    statusBox.dataset.state="error";
    statusBox.innerHTML="<strong>Déverrouillage impossible</strong><span>"+escapeHtml(humanError(error))+"</span>";
  }
});

profileForm.addEventListener("submit",async event=>{
  event.preventDefault();
  try{
    const result=await window.IdentityVault.updateProfile(profileFromForm(profileForm));
    render(result);
  }catch(error){alert(humanError(error))}
});

photoInput.addEventListener("change",()=>{
  const file=photoInput.files?.[0];
  if(!file)return;
  if(!["image/png","image/jpeg","image/webp"].includes(file.type)){
    alert("Formats acceptés : PNG, JPEG ou WebP.");
    photoInput.value="";
    return;
  }
  if(file.size>2*1024*1024){
    alert("La photo doit faire moins de 2 Mo.");
    photoInput.value="";
    return;
  }
  const reader=new FileReader();
  reader.onload=()=>setPhoto(String(reader.result||""));
  reader.onerror=()=>alert("Impossible de lire cette photo.");
  reader.readAsDataURL(file);
});

photoRemove.addEventListener("click",()=>{
  photoInput.value="";
  setPhoto("");
});

lockButton.addEventListener("click",async()=>render(await window.IdentityVault.lock()));
revealButton.addEventListener("click",()=>window.IdentityVault.revealLocation());

refresh();
setInterval(refresh,1500);
