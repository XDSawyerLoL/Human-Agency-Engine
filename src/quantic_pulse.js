import mysql from "mysql2/promise";

let pulsePromise = null;
const rateBuckets = new Map();

function getMysqlConfig(env = process.env) {
  let parsed = null;
  const raw = String(env.MYSQL_URL || env.DATABASE_URL || "").trim();
  if (raw) {
    try {
      const url = new URL(raw);
      if (url.protocol === "mysql:" || url.protocol === "mariadb:") {
        parsed = {
          host: url.hostname,
          port: Number.parseInt(url.port || "3306", 10) || 3306,
          user: decodeURIComponent(url.username || ""),
          password: decodeURIComponent(url.password || ""),
          database: decodeURIComponent(String(url.pathname || "").replace(/^\//, "")),
        };
      }
    } catch {}
  }
  const config = {
    host: String(env.MYSQL_HOST || env.DB_HOST || parsed?.host || "").trim(),
    port: Math.max(1, Math.min(65535, Number.parseInt(String(env.MYSQL_PORT || env.DB_PORT || parsed?.port || "3306"), 10) || 3306)),
    user: String(env.MYSQL_USER || env.DB_USER || parsed?.user || "").trim(),
    password: String(env.MYSQL_PASSWORD || env.DB_PASSWORD || parsed?.password || ""),
    database: String(env.MYSQL_DATABASE || env.DB_NAME || parsed?.database || "").trim(),
  };
  return config.host && config.user && config.database ? config : null;
}

function clean(value, max) {
  return String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

function handle(value) {
  return clean(value, 32).replace(/^@+/, "").toLowerCase().replace(/[^a-z0-9_.-]/g, "") || "quantic";
}

function idOf(value) {
  const id = Number.parseInt(String(value || ""), 10);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function allowWrite(req) {
  const key = String(req.ip || req.socket?.remoteAddress || "anonymous");
  const now = Date.now();
  const bucket = rateBuckets.get(key);
  if (!bucket || now - bucket.startedAt >= 60000) {
    rateBuckets.set(key, { startedAt: now, count: 1 });
    return true;
  }
  bucket.count += 1;
  return bucket.count <= 24;
}

async function initialize() {
  const config = getMysqlConfig();
  if (!config) return null;
  const pool = mysql.createPool({ ...config, waitForConnections: true, connectionLimit: 5, queueLimit: 0, charset: "utf8mb4" });

  await pool.query("CREATE TABLE IF NOT EXISTS quantic_pulse_posts (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, author VARCHAR(80) NOT NULL, handle VARCHAR(32) NOT NULL, body VARCHAR(500) NOT NULL, reply_to BIGINT UNSIGNED NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), KEY idx_pulse_created (created_at, id), KEY idx_pulse_reply (reply_to), CONSTRAINT fk_pulse_reply FOREIGN KEY (reply_to) REFERENCES quantic_pulse_posts(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
  await pool.query("CREATE TABLE IF NOT EXISTS quantic_pulse_likes (post_id BIGINT UNSIGNED NOT NULL, actor VARCHAR(64) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (post_id, actor), CONSTRAINT fk_pulse_like_post FOREIGN KEY (post_id) REFERENCES quantic_pulse_posts(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

  return { pool };
}

async function runtime() {
  if (!pulsePromise) {
    pulsePromise = initialize().catch((error) => {
      pulsePromise = null;
      throw error;
    });
  }
  return pulsePromise;
}

async function readFeed(pool, limit, before) {
  const params = [];
  let where = "";
  if (before) {
    where = "WHERE p.id < ?";
    params.push(before);
  }
  params.push(limit);
  const sql = "SELECT p.id,p.author,p.handle,p.body,p.reply_to AS replyTo,p.created_at AS createdAt,(SELECT COUNT(*) FROM quantic_pulse_likes l WHERE l.post_id=p.id) AS likes,(SELECT COUNT(*) FROM quantic_pulse_posts r WHERE r.reply_to=p.id) AS replies FROM quantic_pulse_posts p " + where + " ORDER BY p.id DESC LIMIT ?";
  const [rows] = await pool.query(sql, params);
  return rows.map((row) => ({
    ...row,
    id: Number(row.id),
    replyTo: row.replyTo == null ? null : Number(row.replyTo),
    likes: Number(row.likes || 0),
    replies: Number(row.replies || 0),
  }));
}

export function installQuanticPulse(app) {
  if (app.__quanticPulseInstalled) return;
  app.__quanticPulseInstalled = true;

  app.get("/api/pulse/health", async (_req, res) => {
    try {
      const state = await runtime();
      if (!state) return res.status(503).json({ status: "unavailable", storage: "mysql-not-configured" });
      await state.pool.query("SELECT 1");
      res.json({ status: "ok", service: "quantic-pulse", storage: "mysql" });
    } catch (error) {
      console.error("[quantic-pulse:health]", error?.message || error);
      res.status(503).json({ status: "unavailable", service: "quantic-pulse" });
    }
  });

  app.get("/api/pulse/feed", async (req, res) => {
    try {
      const state = await runtime();
      if (!state) return res.status(503).json({ error: "Pulse MySQL indisponible." });
      const limit = Math.max(1, Math.min(50, Number.parseInt(String(req.query.limit || "30"), 10) || 30));
      const before = idOf(req.query.before);
      const posts = await readFeed(state.pool, limit, before);
      res.set("Cache-Control", "no-store");
      res.json({ posts, nextBefore: posts.length === limit ? posts.at(-1)?.id ?? null : null });
    } catch (error) {
      console.error("[quantic-pulse:feed]", error?.message || error);
      res.status(503).json({ error: "Le fil Pulse est temporairement indisponible." });
    }
  });

  app.post("/api/pulse/posts", async (req, res) => {
    if (!allowWrite(req)) return res.status(429).json({ error: "Trop de publications. Réessaie dans une minute." });
    const author = clean(req.body?.author, 80) || "Membre Quantic";
    const userHandle = handle(req.body?.handle);
    const body = clean(req.body?.body, 500);
    const replyTo = idOf(req.body?.replyTo);
    if (!body) return res.status(400).json({ error: "Le message est vide." });

    try {
      const state = await runtime();
      if (!state) return res.status(503).json({ error: "Pulse MySQL indisponible." });
      if (replyTo) {
        const [parent] = await state.pool.query("SELECT id FROM quantic_pulse_posts WHERE id=? LIMIT 1", [replyTo]);
        if (!parent.length) return res.status(404).json({ error: "Publication d'origine introuvable." });
      }
      const [result] = await state.pool.execute("INSERT INTO quantic_pulse_posts (author,handle,body,reply_to) VALUES (?,?,?,?)", [author, userHandle, body, replyTo]);
      const id = Number(result.insertId);
      const [rows] = await state.pool.query("SELECT id,author,handle,body,reply_to AS replyTo,created_at AS createdAt FROM quantic_pulse_posts WHERE id=?", [id]);
      const post = rows[0] || {};
      res.status(201).json({ post: { ...post, id, replyTo: post.replyTo == null ? null : Number(post.replyTo), likes: 0, replies: 0 } });
    } catch (error) {
      console.error("[quantic-pulse:create]", error?.message || error);
      res.status(503).json({ error: "Publication impossible pour le moment." });
    }
  });

  app.post("/api/pulse/posts/:id/like", async (req, res) => {
    if (!allowWrite(req)) return res.status(429).json({ error: "Trop d'actions. Réessaie dans une minute." });
    const postId = idOf(req.params.id);
    const actor = clean(req.body?.actor, 64);
    if (!postId || !actor) return res.status(400).json({ error: "Identifiant de réaction invalide." });

    try {
      const state = await runtime();
      if (!state) return res.status(503).json({ error: "Pulse MySQL indisponible." });
      const [existing] = await state.pool.query("SELECT 1 FROM quantic_pulse_likes WHERE post_id=? AND actor=? LIMIT 1", [postId, actor]);
      let liked = false;
      if (existing.length) {
        await state.pool.execute("DELETE FROM quantic_pulse_likes WHERE post_id=? AND actor=?", [postId, actor]);
      } else {
        await state.pool.execute("INSERT INTO quantic_pulse_likes (post_id,actor) VALUES (?,?)", [postId, actor]);
        liked = true;
      }
      const [counts] = await state.pool.query("SELECT COUNT(*) AS likes FROM quantic_pulse_likes WHERE post_id=?", [postId]);
      res.json({ liked, likes: Number(counts[0]?.likes || 0) });
    } catch (error) {
      console.error("[quantic-pulse:like]", error?.message || error);
      res.status(503).json({ error: "Réaction impossible pour le moment." });
    }
  });
}
