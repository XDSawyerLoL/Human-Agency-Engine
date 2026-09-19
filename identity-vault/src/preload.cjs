const {contextBridge,ipcRenderer}=require("electron");

contextBridge.exposeInMainWorld("IdentityVault",{
  status:()=>ipcRenderer.invoke("vault:status"),
  create:(options)=>ipcRenderer.invoke("vault:create",options),
  createHardware:(options)=>ipcRenderer.invoke("vault:create-hardware",options),
  loadFile:()=>ipcRenderer.invoke("vault:load-file"),
  unlock:()=>ipcRenderer.invoke("vault:unlock"),
  unlockHardware:(options)=>ipcRenderer.invoke("vault:unlock-hardware",options),
  updateProfile:(profile,hardwareVaultKey="")=>ipcRenderer.invoke("vault:update-profile",{profile,hardwareVaultKey}),
  lock:()=>ipcRenderer.invoke("vault:lock"),
  hardwareDisconnected:(deviceId="")=>ipcRenderer.invoke("vault:hardware-disconnected",{deviceId}),
  revealLocation:()=>ipcRenderer.invoke("vault:reveal-location"),
  onHardwareSignRequest:(handler)=>{
    if(typeof handler!=="function")return()=>{};
    const listener=(_event,payload)=>handler(payload);
    ipcRenderer.on("hardware:sign-request",listener);
    return()=>ipcRenderer.removeListener("hardware:sign-request",listener);
  },
  respondHardwareSign:(response)=>ipcRenderer.send("hardware:sign-response",response)
});
