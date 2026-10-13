/* URL-safe Base64 without Node's optional "base64url" Buffer encoding.
 * Used by both Quantic ID and SOCIAL; strict round-trip rejects corrupt keys.
 */
export function encodeBase64Url(value){
  return Buffer.from(value).toString('base64').replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
export function decodeBase64Url(value){
  if(typeof value!=='string'||!value||!/^[A-Za-z0-9_-]+$/.test(value)||value.length%4===1)throw new TypeError('invalid_base64url');
  const base64=value.replace(/-/g,'+').replace(/_/g,'/');
  const bytes=Buffer.from(base64+'='.repeat((4-base64.length%4)%4),'base64');
  if(encodeBase64Url(bytes)!==value)throw new TypeError('invalid_base64url');
  return bytes;
}
