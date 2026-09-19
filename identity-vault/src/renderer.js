const $=(selector)=>document.querySelector(selector);
const statusBox=$("#status");
const createForm=$("#create-form");
const unlockForm=$("#unlock-form");
const profileForm=$("#profile-form");
const modeText=$("#mode");
const locationText=$("#location");
const lockButton=$("#lock");
const revealButton=$("#reveal");
const loadVaultButton=$("#load-vault");
const appVersionText=$("#app-version");
const portablePass=$("#portable-pass-wrap");
const portableUnlock=$("#portable-unlock-wrap");
const photoInput=$("#photo-input");
const photoPreview=$("#photo-preview");
const photoPlaceholder=$("#photo-placeholder");
const photoRemove=$("#photo-remove");
let profilePhotoDataUrl="";

function humanError(error){
  const code=String(error?.message||error||"");
  const map={
    portable_passphrase_too_short:"Le code local doit contenir au moins 8 caractères.",
    system_encryption_unavailable:"Le chiffrement système Windows n’est pas disponible.",
    vault_not_found:"Aucun coffre n’existe encore.",
    vault_format_invalid:"Ce fichier n’est pas un coffre Quantic Identity Vault valide.",
    portable_vault_format_invalid:"Le coffre USB n’utilise pas un format de chiffrement compatible.",
    portable_unlock_failed:"Impossible de déverrouiller ce coffre. Vérifiez le code local. Si le code est correct, rechargez le bon fichier de coffre.",
    pc_unlock_failed:"Ce coffre PC ne peut pas être déchiffré sur ce compte Windows.",
    profile_photo_invalid:"La photo sélectionnée n’est pas dans un format accepté.",
    profile_photo_too_large:"La photo est trop volumineuse. Utilisez une image de moins de 2 Mo.",
    identity_locked:"Déverrouillez d’abord l’identité.",
    UnsupportedState:"Le coffre ne peut pas être déchiffré sur ce compte Windows."
  };
  if(/portable_unlock_failed|Unsupported state|authenticate data|bad decrypt|unable to authenticate/i.test(code))return"Impossible de déverrouiller ce coffre. Vérifiez le code local puis, si nécessaire, utilisez « Charger / changer de coffre » pour sélectionner le bon fichier.";
  if(/pc_unlock_failed/i.test(code))return"Ce coffre PC ne peut pas être déchiffré sur ce compte Windows.";
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
  modeText.textContent=status.vaultMode==="portable"?"Mode portable · clé USB":"Mode PC · chiffrement Windows";
  locationText.textContent=status.vaultPath||"";
  document.body.dataset.mode=status.vaultMode;
  portablePass.hidden=status.vaultMode!=="portable";
  portableUnlock.hidden=status.vaultMode!=="portable";

  if(status.identityAvailable){
    statusBox.dataset.state="ready";
    statusBox.innerHTML="<strong>Quantic ID déverrouillé</strong><span>"+escapeHtml(status.label||status.keyId)+"</span><small>"+escapeHtml(status.keyId||"")+"</small>";
    createForm.hidden=true;
    unlockForm.hidden=true;
    profileForm.hidden=false;
    lockButton.hidden=false;
    setProfileForm(status.profile||{});
  }else if(status.vaultExists){
    statusBox.dataset.state="locked";
    statusBox.innerHTML="<strong>Coffre chargé · identité verrouillée</strong><span>Le fichier est chargé sans code. Saisissez le code local uniquement pour ouvrir les données privées.</span>";
    createForm.hidden=true;
    unlockForm.hidden=false;
    profileForm.hidden=true;
    lockButton.hidden=true;
  }else{
    statusBox.dataset.state="empty";
    statusBox.innerHTML="<strong>Aucune identité chargée</strong><span>Chargez un coffre existant ou créez une nouvelle identité.</span>";
    createForm.hidden=false;
    unlockForm.hidden=true;
    profileForm.hidden=true;
    lockButton.hidden=true;
  }
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
      passphrase:data.get("passphrase"),
      profile:basicProfileFromCreate()
    });
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
  }catch(error){
    const message=humanError(error);
    statusBox.dataset.state="error";
    statusBox.innerHTML="<strong>Déverrouillage impossible</strong><span>"+escapeHtml(message)+"</span>";
    const input=unlockForm.elements.namedItem("passphrase");
    input?.focus();
    input?.select?.();
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
