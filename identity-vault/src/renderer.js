const $=(selector)=>document.querySelector(selector);
const statusBox=$("#status");
const createForm=$("#create-form");
const createNote=$("#create-note");
const unlockCard=$("#unlock-card");
const unlockIntro=$("#unlock-intro");
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
const hardwareCard=$("#hardware-card");
const hardwareState=$("#hardware-state");
const hardwarePair=$("#hardware-pair");
const hardwareCreate=$("#hardware-create");
let profilePhotoDataUrl="";
let lastStatus=null;
let pairedHardware=null;
let hardwareProbeBusy=false;

function humanError(error){
  const code=String(error?.message||error||"");
  const map={
    system_encryption_unavailable:"Le chiffrement système Windows n’est pas disponible.",
    vault_not_found:"Aucun coffre n’existe encore.",
    vault_format_invalid:"Ce fichier n’est pas un coffre Quantic Identity Vault valide.",
    usb_key_missing:"Le fichier d’accès de la clé USB est absent.",
    usb_key_invalid:"Le fichier d’accès USB est invalide.",
    usb_vault_unlock_failed:"Le coffre et le fichier d’accès USB ne correspondent pas.",
    legacy_vault_requires_code:"Cet ancien coffre a été créé avec l’ancien système de code local.",
    pc_unlock_failed:"Ce coffre PC ne peut pas être déchiffré sur ce compte Windows.",
    profile_photo_invalid:"La photo sélectionnée n’est pas dans un format accepté.",
    profile_photo_too_large:"La photo est trop volumineuse. Utilisez une image de moins de 2 Mo.",
    identity_locked:"Déverrouillez d’abord l’identité.",
    hardware_webhid_unavailable:"L’accès USB HID n’est pas disponible dans cette version.",
    hardware_device_not_selected:"Aucune Quantic Hardware Key n’a été sélectionnée.",
    hardware_device_not_paired:"Aucune Quantic Hardware Key autorisée n’est connectée.",
    hardware_device_mismatch:"La clé Hardware connectée n’est pas celle liée à cette identité.",
    hardware_device_invalid:"Le périphérique connecté n’est pas une Quantic Hardware Key.",
    hardware_protocol_invalid:"La clé Hardware utilise un protocole incompatible.",
    hardware_request_timeout:"La clé Hardware ne répond pas.",
    hardware_provision_invalid:"La clé Hardware n’a pas pu créer l’identité.",
    hardware_unlock_invalid:"La réponse de déverrouillage matériel est invalide.",
    hardware_signature_invalid:"La signature matérielle est invalide.",
    hardware_vault_key_invalid:"La clé Hardware n’a pas fourni de secret de coffre valide.",
    hardware_vault_key_required:"Reconnectez la Quantic Hardware Key pour enregistrer le profil.",
    hardware_vault_unlock_failed:"La clé Hardware ne peut pas ouvrir ce coffre.",
    hardware_unlock_required:"Cette identité exige la Quantic Hardware Key.",
    hardware_portable_required:"Le mode Hardware se crée depuis la version portable USB."
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
  return {firstName:String(data.get("firstName")||""),lastName:String(data.get("lastName")||"")};
}
function hardwareText(text,state="idle"){
  if(!hardwareState)return;
  hardwareState.dataset.state=state;
  hardwareState.textContent=text;
}
function render(status){
  lastStatus=status;
  appVersionText.textContent=status.appVersion?"v"+status.appVersion:"";
  modeText.textContent=status.hardwareMode
    ?"Quantic Hardware · P-256 · privée non exportable"
    :status.vaultMode==="portable"?"Mode portable · présence USB":"Mode PC · chiffrement Windows";
  locationText.textContent=status.vaultPath||"";
  document.body.dataset.mode=status.vaultMode;

  createForm.hidden=true;
  unlockCard.hidden=true;
  profileForm.hidden=true;
  lockButton.hidden=true;
  hardwareCard.hidden=status.vaultMode!=="portable";

  if(status.hardwareMode){
    hardwareCreate.hidden=true;
    hardwarePair.textContent="Reconnecter la clé Hardware";
    hardwareText(status.identityAvailable
      ?"Hardware actif · la clé privée reste dans le composant sécurisé."
      :"Identité liée à "+(status.hardwareDeviceId||"la Quantic Hardware Key")+".","hardware");
  }else if(status.vaultMode==="portable"){
    hardwareCreate.hidden=false;
    hardwareCreate.disabled=!pairedHardware;
    hardwarePair.textContent=pairedHardware?"Clé Hardware associée":"Associer une clé Hardware";
    if(pairedHardware)hardwareText("Clé détectée · "+pairedHardware.deviceId,"ready");
    else hardwareText("Option renforcée : identité non copiable avec une Quantic Hardware Key.","idle");
  }

  if(status.identityAvailable){
    statusBox.dataset.state="ready";
    const hardware=status.hardwareMode?" · HARDWARE":"";
    statusBox.innerHTML="<strong>Quantic ID déverrouillé"+hardware+"</strong><span>"+escapeHtml(status.label||status.keyId)+"</span><small>"+escapeHtml(status.keyId||"")+"</small>";
    profileForm.hidden=false;
    lockButton.hidden=false;
    setProfileForm(status.profile||{});
    return;
  }

  if(status.legacyVault){
    statusBox.dataset.state="error";
    statusBox.innerHTML="<strong>Ancien coffre protégé par code</strong><span>Il est conservé et sera sauvegardé avant toute nouvelle identité.</span>";
    createNote.textContent="Un nouveau coffre USB sans code peut être créé. L’ancien coffre sera sauvegardé avant remplacement.";
    createForm.hidden=false;
    return;
  }

  if(status.hardwareMode){
    statusBox.dataset.state="locked";
    statusBox.innerHTML="<strong>Identity Vault Hardware verrouillé</strong><span>Connectez la Quantic Hardware Key liée à cette identité, puis cliquez sur Déverrouiller.</span>";
    unlockIntro.textContent="La clé privée n’existe pas dans le coffre USB. La Quantic Hardware Key doit signer physiquement les preuves.";
    unlockCard.hidden=false;
    return;
  }

  if(status.vaultExists&&status.vaultMode==="portable"){
    if(status.usbPresenceAvailable){
      statusBox.dataset.state="locked";
      statusBox.innerHTML="<strong>Identity Vault verrouillé</strong><span>Clé USB détectée. Cliquez simplement sur Déverrouiller.</span>";
      unlockIntro.textContent="La clé USB est détectée. Aucun code n’est nécessaire.";
      unlockCard.hidden=false;
    }else{
      statusBox.dataset.state="error";
      statusBox.innerHTML="<strong>Clé USB incomplète</strong><span>Le coffre est présent mais son fichier d’accès logiciel est absent.</span>";
    }
    return;
  }

  if(status.vaultExists){
    statusBox.dataset.state="locked";
    statusBox.innerHTML="<strong>Identity Vault verrouillé</strong><span>Cliquez sur Déverrouiller.</span>";
    unlockIntro.textContent="Déverrouillage local.";
    unlockCard.hidden=false;
    return;
  }

  statusBox.dataset.state="empty";
  statusBox.innerHTML="<strong>Aucune identité</strong><span>Créez votre Quantic ID ou associez une Quantic Hardware Key.</span>";
  createNote.textContent="Le mode USB standard ne demande aucun code local. Le mode Hardware conserve la clé privée hors du stockage USB.";
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
    const result=await window.IdentityVault.create({label:data.get("label"),profile:basicProfileFromCreate()});
    render(result);
    createForm.reset();
  }catch(error){alert(humanError(error))}
});

unlockButton.addEventListener("click",async()=>{
  try{
    if(lastStatus?.hardwareMode){
      const unlocked=await window.QuanticHardware.unlock(lastStatus.hardwareDeviceId);
      render(await window.IdentityVault.unlockHardware(unlocked));
    }else{
      render(await window.IdentityVault.unlock());
    }
  }catch(error){
    statusBox.dataset.state="error";
    statusBox.innerHTML="<strong>Déverrouillage impossible</strong><span>"+escapeHtml(humanError(error))+"</span>";
  }
});

profileForm.addEventListener("submit",async event=>{
  event.preventDefault();
  try{
    let hardwareVaultKey="";
    if(lastStatus?.hardwareMode){
      const unlocked=await window.QuanticHardware.unlock(lastStatus.hardwareDeviceId);
      hardwareVaultKey=unlocked.vaultKey;
    }
    const result=await window.IdentityVault.updateProfile(profileFromForm(profileForm),hardwareVaultKey);
    render(result);
  }catch(error){alert(humanError(error))}
});

hardwarePair.addEventListener("click",async()=>{
  try{
    hardwareText("Recherche de la Quantic Hardware Key…","checking");
    pairedHardware=await window.QuanticHardware.pair();
    hardwareText("Clé détectée · "+pairedHardware.deviceId,"ready");
    hardwareCreate.disabled=false;
    if(lastStatus?.hardwareMode)await refresh();
  }catch(error){
    pairedHardware=null;
    hardwareCreate.disabled=true;
    hardwareText(humanError(error),"error");
  }
});

hardwareCreate.addEventListener("click",async()=>{
  try{
    if(!pairedHardware)pairedHardware=await window.QuanticHardware.pair();
    const warning="Une identité Hardware utilise une nouvelle clé cryptographique non exportable. Votre coffre actuel sera sauvegardé, mais le Quantic ID changera. Continuer ?";
    if(!confirm(warning))return;
    hardwareText("Création de la clé privée dans le composant sécurisé…","checking");
    const provision=await window.QuanticHardware.provision();
    const profile=lastStatus?.identityAvailable?profileFromForm(profileForm):basicProfileFromCreate();
    const label=lastStatus?.label||String(new FormData(createForm).get("label")||"Mon identité Quantic Hardware");
    const result=await window.IdentityVault.createHardware({...provision,label,profile});
    pairedHardware={deviceId:provision.deviceId};
    render(result);
    hardwareText("Quantic Hardware actif · clé privée non exportable.","ready");
  }catch(error){
    hardwareText(humanError(error),"error");
  }
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

photoRemove.addEventListener("click",()=>{photoInput.value="";setPhoto("");});
lockButton.addEventListener("click",async()=>render(await window.IdentityVault.lock()));
revealButton.addEventListener("click",()=>window.IdentityVault.revealLocation());

window.IdentityVault.onHardwareSignRequest(async request=>{
  try{
    const signature=await window.QuanticHardware.sign(request.payload,request.deviceId);
    window.IdentityVault.respondHardwareSign({id:request.id,deviceId:request.deviceId,signature});
  }catch(error){
    window.IdentityVault.respondHardwareSign({id:request.id,deviceId:request.deviceId,error:String(error?.message||error)});
  }
});

window.addEventListener("quantic-hardware-disconnect",async()=>{
  pairedHardware=null;
  hardwareCreate.disabled=true;
  try{render(await window.IdentityVault.hardwareDisconnected(lastStatus?.hardwareDeviceId||""))}catch{}
  hardwareText("Clé Hardware retirée · identité verrouillée.","error");
});

async function hardwarePresenceCheck(){
  if(hardwareProbeBusy||!lastStatus?.hardwareMode||!lastStatus?.identityAvailable)return;
  hardwareProbeBusy=true;
  try{
    pairedHardware=await window.QuanticHardware.reconnect(lastStatus.hardwareDeviceId);
  }catch{
    pairedHardware=null;
    try{render(await window.IdentityVault.hardwareDisconnected(lastStatus.hardwareDeviceId))}catch{}
  }finally{hardwareProbeBusy=false}
}

refresh();
setInterval(refresh,1500);
setInterval(hardwarePresenceCheck,4000);
