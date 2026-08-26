import mysql from 'mysql2/promise';
import { config } from './config.js';

const HISTORY_MAX_POINTS = 72;

export class EvidenceStore {
  constructor() {
    this.snapshot = null;
    this.history = new Map();
    this.pool = null;
    this.mode = 'memory';
  }

  async init() {
    const c = config.mysql;
    if (!c.host || !c.user || !c.database) return;
    try {
      this.pool = mysql.createPool({
        host: c.host,
        port: c.port,
        user: c.user,
        password: c.password,
        database: c.database,
        connectionLimit: 3,
        enableKeepAlive: true,
        charset: 'utf8mb4'
      });
      await this.pool.query(`CREATE TABLE IF NOT EXISTS evidence_state (
        state_key VARCHAR(64) PRIMARY KEY,
        payload JSON NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
      await this.pool.query(`CREATE TABLE IF NOT EXISTS evidence_history (
        scenario_key VARCHAR(96) NOT NULL,
        observed_at DATETIME(3) NOT NULL,
        probability DECIMAL(6,4) NOT NULL,
        low DECIMAL(6,4) NOT NULL,
        high DECIMAL(6,4) NOT NULL,
        PRIMARY KEY (scenario_key, observed_at),
        INDEX idx_history_scenario_time (scenario_key, observed_at)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
      const [rows] = await this.pool.query('SELECT payload FROM evidence_state WHERE state_key = ?', ['snapshot']);
      if (rows?.[0]?.payload) this.snapshot = typeof rows[0].payload === 'string' ? JSON.parse(rows[0].payload) : rows[0].payload;
      this.mode = 'mysql';
    } catch (error) {
      console.error('[store] MySQL indisponible, mémoire seule:', error.message);
      this.pool = null;
      this.mode = 'memory';
    }
  }

  async getSnapshot() {
    return this.snapshot;
  }

  async appendHistory(forecasts, at) {
    for (const f of forecasts) {
      const point = { at, percent: f.probability.percent, interval_percent: f.probability.interval_percent };
      const arr = this.history.get(f.scenario_key) ?? [];
      arr.push(point);
      this.history.set(f.scenario_key, arr.slice(-HISTORY_MAX_POINTS));
    }

    if (!this.pool) return;
    try {
      const values = forecasts.map(f => [
        f.scenario_key,
        new Date(at),
        f.probability.estimate,
        f.probability.interval_low,
        f.probability.interval_high
      ]);
      if (values.length) {
        await this.pool.query(
          'INSERT IGNORE INTO evidence_history (scenario_key, observed_at, probability, low, high) VALUES ?',
          [values]
        );
      }
    } catch (error) {
      console.error('[store] historique MySQL:', error.message);
    }
  }

  async attachHistory(forecasts) {
    if (this.pool && forecasts.length) {
      try {
        const keys = forecasts.map(f => f.scenario_key);
        const [rows] = await this.pool.query(
          `SELECT scenario_key, observed_at, probability, low, high
           FROM evidence_history
           WHERE scenario_key IN (?)
           ORDER BY observed_at DESC`,
          [keys]
        );
        const grouped = new Map();
        for (const row of rows) {
          const arr = grouped.get(row.scenario_key) ?? [];
          if (arr.length < HISTORY_MAX_POINTS) {
            arr.push({
              at: new Date(row.observed_at).toISOString(),
              percent: Math.round(Number(row.probability) * 100),
              interval_percent: [Math.round(Number(row.low) * 100), Math.round(Number(row.high) * 100)]
            });
            grouped.set(row.scenario_key, arr);
          }
        }
        for (const f of forecasts) {
          const db = (grouped.get(f.scenario_key) ?? []).reverse();
          const mem = this.history.get(f.scenario_key) ?? [];
          f.probability_history = db.length ? db : mem;
        }
        return forecasts;
      } catch (error) {
        console.error('[store] lecture historique MySQL:', error.message);
      }
    }
    for (const f of forecasts) f.probability_history = this.history.get(f.scenario_key) ?? [];
    return forecasts;
  }

  async saveSnapshot(snapshot) {
    this.snapshot = snapshot;
    if (!this.pool) return;
    try {
      await this.pool.query(
        `INSERT INTO evidence_state (state_key, payload) VALUES ('snapshot', ?)
         ON DUPLICATE KEY UPDATE payload = VALUES(payload), updated_at = CURRENT_TIMESTAMP`,
        [JSON.stringify(snapshot)]
      );
    } catch (error) {
      console.error('[store] snapshot MySQL:', error.message);
    }
  }
}
