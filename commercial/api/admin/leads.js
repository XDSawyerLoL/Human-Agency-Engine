import {db,respond,verifyAdmin} from '../_util.js';
export default async function handler(req,res){
  if(!verifyAdmin(req))return respond(res,401,{error:'Non autorisé'});
  if(req.method!=='GET')return respond(res,405,{error:'Méthode non autorisée'});
  try{
    const rows=await db()`SELECT id,created_at,name,email,company,sector,interest,details,utm_source,utm_medium,utm_campaign,consent_marketing,status FROM leads ORDER BY created_at DESC LIMIT 400`;
    return respond(res,200,{leads:rows});
  }catch(e){console.error('Admin leads error',e?.message);return respond(res,503,{error:'Base indisponible'});}
}