import {db,respond,verifyAdmin} from '../_util.js';
export default async function handler(req,res) {
  if (!verifyAdmin(req)) return respond(res,401,{error:'Non autorisé'});
  if (req.method !== 'GET') return respond(res,405,{error:'Méthode non autorisée'});
  try {
    const sql=db();
    const check=await sql`SELECT now() AS checked_at, (SELECT COUNT(*)::int FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('leads','partner_targets','audit_events')) AS tables_ready`;
    return respond(res,200,{ok:check[0].tables_ready===3,database:check[0].tables_ready===3?'accessible':'schéma incomplet',checked_at:check[0].checked_at,expected_tables:3,tables_found:check[0].tables_ready,payments:'non intégrés',social_metrics:'à consulter dans Metricool'});
  } catch (error) {
    console.error('Admin health check failed', error?.message);
    return respond(res,503,{ok:false,database:'indisponible'});
  }
}