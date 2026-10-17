import {db, respond, verifyAdmin} from '../_util.js';
export default async function handler(req,res) {
  if(!verifyAdmin(req))return respond(res,401,{error:'Non autorisé'});
  if(req.method!=='GET')return respond(res,405,{error:'Méthode non autorisée'});
  try{
    const partners=await db()`SELECT id,name,website,category,rationale,status,verified_on,created_at FROM partner_targets ORDER BY created_at DESC, id DESC LIMIT 500`;
    return respond(res,200,{partners, note:'Cibles vérifiées sur leurs sites publics ; aucune relation commerciale présumée.'});
  } catch(e){console.error('Partner pipeline error',e?.message);return respond(res,503,{error:'Réseau momentanément indisponible'});}
}