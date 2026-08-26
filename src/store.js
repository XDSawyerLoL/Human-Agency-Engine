import mysql from 'mysql2/promise';
import { config } from './config.js';

const HISTORY_MAX_POINTS = 72;
const SIGNAL_LEDGER_MAX_CYCLES = 7 * 24 * 6 + 12;
const DAY = 86_400_000;
const clampProbability = p => Math.max(0.001, Math.min(0.999, Number(p) || 0));

export class EvidenceStore {
  constructor() {
    this.snapshot = null;
    this.history = new Map();
    this.registry = new Map();
    this.signalLedger = [];
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
      await this.pool.query(`CREATE TABLE IF NOT EXISTS evidence_forecast_registry (
        scenario_key VARCHAR(96) PRIMARY KEY,
        scenario_id VARCHAR(128) NULL,
        title VARCHAR(500) NOT NULL,
        domain VARCHAR(64) NULL,
        horizon_tier VARCHAR(32) NULL,
        first_seen DATETIME(3) NOT NULL,
        last_seen DATETIME(3) NOT NULL,
        target_at DATETIME(3) NULL,
        first_probability DECIMAL(6,4) NOT NULL,
        last_probability DECIMAL(6,4) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        resolved_at DATETIME(3) NULL,
        outcome TINYINT NULL,
        INDEX idx_registry_target (target_at),
        INDEX idx_registry_status (status)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
      const [rows] = await this.pool.query('SELECT state_key, payload FROM evidence_state WHERE state_key IN (?, ?)', ['snapshot','signal_ledger']);
      for (const row of rows || []) {
        const payload = typeof row.payload === 'string' ? JSON.parse(row.payload) : row.payload;
        if (row.state_key === 'snapshot') this.snapshot = payload;
        if (row.state_key === 'signal_ledger' && Array.isArray(payload)) this.signalLedger = payload;
      }
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

  async recordForecastRegistry(forecasts, at) {
    const seenAt = new Date(at);
    for (const f of forecasts) {
      const old = this.registry.get(f.scenario_key);
      const firstProbability = old?.first_probability ?? Number(f.probability?.estimate ?? 0);
      this.registry.set(f.scenario_key, {
        scenario_key: f.scenario_key,
        scenario_id: f.scenario_id ?? null,
        title: f.title ?? f.headline ?? 'Scénario',
        domain: f.domain ?? null,
        horizon_tier: f.horizon_tier ?? null,
        first_seen: old?.first_seen ?? at,
        last_seen: at,
        target_at: f.target_date ?? f.time_window?.end_at ?? null,
        first_probability: firstProbability,
        last_probability: Number(f.probability?.estimate ?? 0),
        status: f.status ?? 'active',
        resolved_at: old?.resolved_at ?? null,
        outcome: old?.outcome ?? null
      });
    }

    if (!this.pool || !forecasts.length) return;
    try {
      for (const f of forecasts) {
        const targetRaw = f.target_date ?? f.time_window?.end_at ?? null;
        const target = targetRaw ? new Date(targetRaw) : null;
        await this.pool.query(
          `INSERT INTO evidence_forecast_registry
           (scenario_key, scenario_id, title, domain, horizon_tier, first_seen, last_seen, target_at, first_probability, last_probability, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON DUPLICATE KEY UPDATE
             scenario_id=VALUES(scenario_id), title=VALUES(title), domain=VALUES(domain), horizon_tier=VALUES(horizon_tier),
             last_seen=VALUES(last_seen), target_at=VALUES(target_at), last_probability=VALUES(last_probability), status=VALUES(status)`,
          [
            f.scenario_key, f.scenario_id ?? null, String(f.title ?? f.headline ?? 'Scénario').slice(0,500), f.domain ?? null, f.horizon_tier ?? null,
            seenAt, seenAt, target && !Number.isNaN(target.getTime()) ? target : null,
            Number(f.probability?.estimate ?? 0), Number(f.probability?.estimate ?? 0), f.status ?? 'active'
          ]
        );
      }
    } catch (error) {
      console.error('[store] registre prédictions MySQL:', error.message);
    }
  }

  async recordSignalCycle(cycle) {
    if (!cycle?.at) return;
    const cutoff = Date.now() - 7 * DAY;
    this.signalLedger.push(cycle);
    this.signalLedger = this.signalLedger
      .filter(x => Date.parse(x.at || 0) >= cutoff)
      .slice(-SIGNAL_LEDGER_MAX_CYCLES);
    if (!this.pool) return;
    try {
      await this.pool.query(
        `INSERT INTO evidence_state (state_key, payload) VALUES ('signal_ledger', ?)
         ON DUPLICATE KEY UPDATE payload = VALUES(payload), updated_at = CURRENT_TIMESTAMP`,
        [JSON.stringify(this.signalLedger)]
      );
    } catch (error) {
      console.error('[store] signal ledger MySQL:', error.message);
    }
  }

  async getSignalAnalytics() {
    const cutoff = Date.now() - 7 * DAY;
    const cycles = this.signalLedger.filter(x => Date.parse(x.at || 0) >= cutoff);
    const byDay = new Map();
    const domains = {};
    const sourceTotals = {};
    const countries = new Set();
    for (const cycle of cycles) {
      const d = new Date(cycle.at);
      const day = Number.isNaN(d.getTime()) ? 'inconnu' : d.toISOString().slice(0,10);
      byDay.set(day, (byDay.get(day) || 0) + Number(cycle.count || 0));
      for (const [key,n] of Object.entries(cycle.domains || {})) domains[key] = (domains[key] || 0) + Number(n || 0);
      for (const [key,n] of Object.entries(cycle.sources || {})) sourceTotals[key] = (sourceTotals[key] || 0) + Number(n || 0);
      for (const c of cycle.countries || []) countries.add(c);
    }
    const last = cycles.at(-1) || null;
    const dates = [...Array(7)].map((_,i)=>new Date(Date.now()-(6-i)*DAY).toISOString().slice(0,10));
    return {
      current_cycle_count:Number(last?.count || 0),
      volume_7d:dates.map(date=>({date,count:Number(byDay.get(date)||0)})),
      domain_distribution:domains,
      source_distribution:sourceTotals,
      countries:[...countries],
      realtime_feed:last?.feed || [],
      cycles_recorded:cycles.length,
      persistent:this.mode === 'mysql'
    };
  }

  async getTrackRecord() {
    const now = Date.now();
    let registryRows = [...this.registry.values()];
    let historyPoints = [...this.history.values()].reduce((sum, arr) => sum + arr.length, 0);
    let multiPoint = [...this.history.values()].filter(arr => arr.length >= 2).length;

    if (this.pool) {
      try {
        const [rows] = await this.pool.query(
          `SELECT scenario_key, scenario_id, title, domain, horizon_tier, first_seen, last_seen, target_at,
                  first_probability, last_probability, status, resolved_at, outcome
           FROM evidence_forecast_registry ORDER BY first_seen DESC LIMIT 500`
        );
        registryRows = rows.map(r => ({...r, first_seen:new Date(r.first_seen).toISOString(), last_seen:new Date(r.last_seen).toISOString(), target_at:r.target_at?new Date(r.target_at).toISOString():null}));
        const [counts] = await this.pool.query('SELECT COUNT(*) AS points, COUNT(DISTINCT scenario_key) AS scenarios FROM evidence_history');
        historyPoints = Number(counts?.[0]?.points ?? historyPoints);
        const [multi] = await this.pool.query('SELECT COUNT(*) AS n FROM (SELECT scenario_key FROM evidence_history GROUP BY scenario_key HAVING COUNT(*) >= 2) x');
        multiPoint = Number(multi?.[0]?.n ?? multiPoint);
      } catch (error) {
        console.error('[store] track record MySQL:', error.message);
      }
    }

    const resolvedRows = registryRows.filter(r => ['resolved','invalidated'].includes(String(r.status)) && [0,1].includes(Number(r.outcome)));
    const resolved = resolvedRows.length;
    const successful = resolvedRows.filter(r => Number(r.outcome)===1).length;
    const failed = resolvedRows.filter(r => Number(r.outcome)===0).length;
    const expiredUnresolved = registryRows.filter(r => r.target_at && new Date(r.target_at).getTime() < now && !['resolved','invalidated'].includes(String(r.status))).length;
    const current = this.snapshot?.forecasts ?? [];
    const bucketDefs = [
      { label:'< 40%', min:0, max:39 }, { label:'40–59%', min:40, max:59 }, { label:'60–79%', min:60, max:79 }, { label:'≥ 80%', min:80, max:100 }
    ];
    const buckets = bucketDefs.map(b => {
      const rows = resolvedRows.filter(r => Number(r.first_probability)*100 >= b.min && Number(r.first_probability)*100 <= b.max);
      return {
        ...b,
        active:current.filter(f => Number(f?.probability?.percent ?? 0) >= b.min && Number(f?.probability?.percent ?? 0) <= b.max).length,
        resolved:rows.length,
        observed_frequency:rows.length ? Math.round(rows.reduce((a,r)=>a+Number(r.outcome),0)/rows.length*1000)/10 : null
      };
    });
    const brier = resolved ? resolvedRows.reduce((sum,r)=>{
      const p=clampProbability(r.first_probability); const y=Number(r.outcome); return sum+(p-y)**2;
    },0)/resolved : null;
    const logLoss = resolved ? resolvedRows.reduce((sum,r)=>{
      const p=clampProbability(r.first_probability); const y=Number(r.outcome); return sum-(y*Math.log(p)+(1-y)*Math.log(1-p));
    },0)/resolved : null;

    return {
      generated_at: new Date().toISOString(),
      storage_mode: this.mode,
      tracked_scenarios: registryRows.length,
      probability_history_points: historyPoints,
      scenarios_with_revisions: multiPoint,
      resolved_scenarios: resolved,
      successful_scenarios: successful,
      failed_scenarios: failed,
      expired_unresolved: expiredUnresolved,
      calibration_ready: resolved >= 30,
      empirical_calibration_enabled: resolved >= 30,
      brier_score: brier === null ? null : Math.round(brier*10000)/10000,
      log_loss: logLoss === null ? null : Math.round(logLoss*10000)/10000,
      hit_rate: resolved ? Math.round(successful / resolved * 1000) / 10 : null,
      buckets,
      resolution_queue:registryRows.filter(r=>r.target_at && new Date(r.target_at).getTime()<now && !['resolved','invalidated'].includes(String(r.status))).slice(0,50),
      recent: registryRows.slice(0,20),
      note: resolved >= 30
        ? 'Calibration empirique calculable sur les scénarios résolus. Les scores reposent sur la probabilité enregistrée à la première publication.'
        : 'Collecte historique en cours. Aucun score de performance n’est inventé avant un nombre suffisant de prédictions réellement résolues.'
    };
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