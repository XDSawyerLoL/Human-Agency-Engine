import {db,respond,verifyAdmin} from '../_util.js';
export default async function handler(req,res){
  if(!verifyAdmin(req))return respond(res,401,{error:'Non autorisé'});
  if(req.method!=='GET')return respond(res,405,{error:'Méthode non autorisée'});
  try{
    const sql=db();
    const [totals,sources]=await Promise.all([
      sql`SELECT count(*)::int AS total,count(*) FILTER (WHERE created_at>=now()-interval '7 days')::int AS last_7_days,count(*) FILTER(WHERE interest='demo')::int AS demos FROM leads`,
      sql`SELECT COALESCE(NULLIF(utm_source,''),'direct') AS source,count(*)::int AS total FROM leads GROUP BY 1 ORDER BY total DESC LIMIT 12`
    ]);
    return respond(res,200,{...totals[0],sources,revenue_status:'non_connecté',social_status:'non_connecté',conversions_status:'non_mesuré'});
  }catch(e){console.error('Stats error',e?.message);return respond(res,503,{error:'Statistiques momentanément indisponibles'});}
}