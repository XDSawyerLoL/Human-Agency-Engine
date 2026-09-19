const {contextBridge,ipcRenderer}=require("electron");
contextBridge.exposeInMainWorld("IdentityVault",{
  status:()=>ipcRenderer.invoke("vault:status"),
  create:(options)=>ipcRenderer.invoke("vault:create",options),
  loadFile:()=>ipcRenderer.invoke("vault:load-file"),
  unlock:()=>ipcRenderer.invoke("vault:unlock"),
  updateProfile:(profile)=>ipcRenderer.invoke("vault:update-profile",{profile}),
  lock:()=>ipcRenderer.invoke("vault:lock"),
  revealLocation:()=>ipcRenderer.invoke("vault:reveal-location")
});
