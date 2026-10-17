import crypto from 'node:crypto';
import { neon } from '@neondatabase/serverless';
export const db = () => {
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL absent');
  return neon(process.env.DATABASE_URL);
};
export const respond = (res, status, body) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  return res.status(status).json(body);
};
export function allowedOrigin(req) {
  const origin = req.headers.origin;
  if (!origin) return true;
  try {
    const u = new URL(origin);
    const host = (req.headers['x-forwarded-host'] || req.headers.host || '').split(',')[0].trim().toLowerCase();
    return u.protocol === 'https:' && u.host.toLowerCase() === host;
  } catch { return false; }
}
export function verifyAdmin(req) {
  const token = process.env.ADMIN_SECRET;
  const value = req.headers.authorization;
  if (!token || !value || !value.startsWith('Bearer ')) return false;
  const received = Buffer.from(value.substring(7));
  const expected = Buffer.from(token);
  return received.length === expected.length && crypto.timingSafeEqual(received, expected);
}
export const plain = (value, max=180) => typeof value === 'string' ? value.trim().slice(0, max) : '';
export const emailValid = email => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) && email.length <= 254;