import {db,respond,verifyAdmin,allowedOrigin} from '../_util.js';
export default async function handler(req,res){
  if(!verifyAdmin(req))return respond(res,401,{error:'Non autorisé'});
  if(req.method!=='POST')return respond(res,405,{error:'Méthode non autorisée'});
  if(!allowedOrigin(req))return respond(res,403,{error:'Origine non autorisée'});
  const id=Number(req.body?.id);
  if(!Number.isSafeInteger(id)||id<=0)return respond(res,400,{error:'Identifiant invalide'});
  try{
    const sql=db();const result=await sql`DELETE FROM leads WHERE id=${id} RETURNING id`;
    if(!result.length)return respond(res,404,{error:'Prospect introuvable'});
    await sql`INSERT INTO audit_events (event_type,metadata) VALUES('lead.deleted',${JSON.stringify({id})}::jsonb)`;
    return respond(res,200,{ok:true});
  }catch(e){console.error('Delete lead error',e?.message);return respond(res,503,{error:'Suppression indisponible'});}
}