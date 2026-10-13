import { db, respond, allowedOrigin, plain, emailValid } from './_util.js';
export default async function handler(req, res) {
  if (req.method !== 'POST') return respond(res, 405, { error: 'Méthode non autorisée' });
  if (!allowedOrigin(req)) return respond(res, 403, { error: 'Origine non autorisée' });
  const body = req.body && typeof req.body === 'object' ? req.body : {};
  if (JSON.stringify(body).length > 8500) return respond(res, 413, {error:'Données trop volumineuses'});
  if (plain(body.website)) return respond(res, 200, {ok: true}); // honeypot
  const name = plain(body.name, 120), company=plain(body.company,160), email=plain(body.email,254).toLowerCase();
  const sector=plain(body.sector,120), details=plain(body.details,1200), interest=plain(body.interest,50);
  const consent=body.consent_marketing === true;
  const accepted=body.accepted_privacy === true;
  if (!name || !company || !sector || !emailValid(email) || !accepted || !['demo','pilot','information','rights'].includes(interest)) {
    return respond(res, 400, {error:'Champs requis incomplets ou invalides'});
  }
  const source=plain(body.source,50)||'landing';
  const utmSource=plain(body.utm_source,100),utmMedium=plain(body.utm_medium,100),utmCampaign=plain(body.utm_campaign,100);
  try {
    const sql=db();
    const recent=await sql`SELECT count(*)::int AS count FROM leads WHERE lower(email)=${email} AND created_at > now() - interval '1 hour'`;
    if (recent[0].count >= 3) return respond(res, 429, {error:'Trop de demandes récentes. Réessayez ultérieurement.'});
    const duplicates=await sql`SELECT id FROM leads WHERE lower(email)=${email} AND interest=${interest} AND details=${details} AND created_at > now() - interval '24 hours' LIMIT 1`;
    if (duplicates.length) return respond(res, 200, {ok:true,duplicate:true});
    const created=await sql`INSERT INTO leads (name,email,company,sector,details,interest,utm_source,utm_medium,utm_campaign,consent_marketing,source)
      VALUES (${name},${email},${company},${sector},${details},${interest},${utmSource},${utmMedium},${utmCampaign},${consent},${source}) RETURNING id`;
    await sql`INSERT INTO audit_events(event_type,lead_id,metadata) VALUES ('lead.created',${created[0].id},${JSON.stringify({interest,source})}::jsonb)`;
    return respond(res, 201, {ok:true});
  } catch (e) {
    console.error('Lead submission failure', e?.message);
    return respond(res, 503, {error:'Le formulaire est momentanément indisponible. Aucun enregistrement confirmé.'});
  }
}