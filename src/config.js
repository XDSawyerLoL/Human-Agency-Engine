const int = (name, fallback, min, max) => {
  const raw = Number.parseInt(process.env[name] ?? '', 10);
  if (!Number.isFinite(raw)) return fallback;
  return Math.max(min, Math.min(max, raw));
};

const value = (...names) => {
  for (const name of names) {
    const v = String(process.env[name] ?? '').trim();
    if (v) return v;
  }
  return '';
};

function mysqlUrlConfig() {
  const raw=value('MYSQL_URL','DATABASE_URL');
  if(!raw) return null;
  try {
    const u=new URL(raw);
    if(!['mysql:','mariadb:'].includes(u.protocol)) return null;
    return {host:u.hostname,port:Number.parseInt(u.port||'3306',10)||3306,user:decodeURIComponent(u.username||''),password:decodeURIComponent(u.password||''),database:decodeURIComponent(String(u.pathname||'').replace(/^\//,''))};
  } catch { return null; }
}

const mysqlUrl=mysqlUrlConfig();
const mysqlPortRaw=value('MYSQL_PORT','DB_PORT');

export const config = {
  port: int('PORT', 3000, 1, 65535),
  refreshMs: int('EVIDENCE_REFRESH_SECONDS', 600, 120, 3600) * 1000,
  maxForecasts: int('EVIDENCE_FORECAST_LIMIT', 96, 72, 144),
  fredApiKey: value('FRED_API_KEY'),
  forecastApiKey: value('FORECAST_API_KEY', 'FORESCAST_API_KEY'),
  windyApiKey: value('WINDY_POINT_FORECAST_API_KEY', 'WINDY_KEY'),
  copernicusApiKey: value('COPERNICUS_API_KEY'),
  pointApiKey: value('POINT_API_KEY'),
  metaculusApiKey: value('METACULUS_API_KEY'),
  footballDataApiKey: value('FOOTBALL_DATA_API_KEY'),
  theSportsDbApiKey: value('THESPORTSDB_API_KEY') || '123',
  ai: {
    baseUrl: value('PROVIDENCE_QWEN_BASE_URL','QWEN_BASE_URL','OPENAI_COMPATIBLE_BASE_URL'),
    apiKey: value('PROVIDENCE_QWEN_API_KEY','QWEN_API_KEY','OPENAI_COMPATIBLE_API_KEY'),
    analystModel: value('PROVIDENCE_QWEN_MODEL','QWEN_MODEL'),
    redTeamModel: value('PROVIDENCE_REDTEAM_MODEL','QWEN_REDTEAM_MODEL'),
    timeoutMs: int('PROVIDENCE_ANALYST_TIMEOUT_MS', 25000, 3000, 60000),
    maxTokens: int('PROVIDENCE_ANALYST_MAX_TOKENS', 900, 128, 2400)
  },
  supabase: {
    url: value('SUPABASE_URL','SUPABASE_PUBLIC_URL'),
    secretKey: value('SUPABASE_API_KEY','SUPABASE_SECRET_KEY','SUPABASE_SERVICE_ROLE_KEY')
  },
  mysql: {
    host: value('MYSQL_HOST', 'DB_HOST') || mysqlUrl?.host || '',
    port: mysqlPortRaw ? Math.max(1,Math.min(65535,Number.parseInt(mysqlPortRaw,10)||3306)) : (mysqlUrl?.port || 3306),
    user: value('MYSQL_USER', 'DB_USER') || mysqlUrl?.user || '',
    password: value('MYSQL_PASSWORD', 'DB_PASSWORD') || mysqlUrl?.password || '',
    database: value('MYSQL_DATABASE', 'DB_NAME') || mysqlUrl?.database || ''
  },
  adminRefreshKey: value('EVIDENCE_ADMIN_KEY')
};

export const providerState = () => ({
  FRED: Boolean(config.fredApiKey),
  ForecastAPI: Boolean(config.forecastApiKey),
  WindyConfiguredButNotUsedAsProductionEvidence: Boolean(config.windyApiKey),
  CopernicusPublic: true,
  MetaculusReferenceOnly: Boolean(config.metaculusApiKey),
  PointReferenceOnly: Boolean(config.pointApiKey),
  FootballDataFixtures: Boolean(config.footballDataApiKey),
  TheSportsDBFallback: Boolean(config.theSportsDbApiKey),
  ProvidenceAnalystConfigured: Boolean(config.ai.baseUrl && config.ai.analystModel),
  ProvidenceRedTeamConfigured: Boolean(config.ai.baseUrl && config.ai.redTeamModel),
  SupabaseDurableMirrorConfigured: Boolean(config.supabase.url && config.supabase.secretKey),
  PersistentLearningConfigured: Boolean(config.mysql.host && config.mysql.user && config.mysql.database)
});