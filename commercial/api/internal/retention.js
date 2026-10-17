import crypto from 'node:crypto';
import { db, respond } from '../_util.js';
function authorized(req) {
  const expected=process.env.CRON_SECRET;
  const received=req.headers.authorization;
  if(!expected || !received || !received.startsWith('Bearer ')) return false;
  const a=Buffer.from(received.slice(7)), b=Buffer.from(expected);
  return a.length===b.length && crypto.timingSafeEqual(a,b);
}
export default async function handler(req,res) {
  if (req.method !== 'GET') return respond(res,405,{error:'Méthode non autorisée'});
  if (!authorized(req)) return respond(res,401,{error:'Non autorisé'});
  try {
    const sql=db();
    const aged=await sql`DELETE FROM leads WHERE created_at < now() - interval '12 months' RETURNING id`;
    await sql`INSERT INTO audit_events (event_type,metadata) VALUES ('retention.executed', ${JSON.stringify({deleted:aged.length})}::jsonb)`;
    return respond(res,200,{ok:true,deleted:aged.length});
  } catch(e){ console.error('Retention job failure',e?.message); return respond(res,503,{error:'Entretien indisponible'}); }
}