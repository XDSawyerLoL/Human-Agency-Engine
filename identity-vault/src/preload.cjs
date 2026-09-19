const {contextBridge,ipcRenderer}=require("electron");
contextBridge.exposeInMainWorld("IdentityVault",{
  status:()=>ipcRenderer.invoke("vault:status"),
  create:(options)=>ipcRenderer.invoke("vault:create",options),
  unlock:(passphrase)=>ipcRenderer.invoke("vault:unlock",{passphrase}),
  lock:()=>ipcRenderer.invoke("vault:lock"),
  revealLocation:()=>ipcRenderer.invoke("vault:reveal-location")
});
