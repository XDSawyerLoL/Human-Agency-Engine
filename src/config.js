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

export const config = {
  port: int('PORT', 3000, 1, 65535),
  refreshMs: int('EVIDENCE_REFRESH_SECONDS', 600, 120, 3600) * 1000,
  maxForecasts: int('EVIDENCE_FORECAST_LIMIT', 20, 5, 30),
  fredApiKey: value('FRED_API_KEY'),
  forecastApiKey: value('FORECAST_API_KEY', 'FORESCAST_API_KEY'),
  windyApiKey: value('WINDY_POINT_FORECAST_API_KEY', 'WINDY_KEY'),
  copernicusApiKey: value('COPERNICUS_API_KEY'),
  pointApiKey: value('POINT_API_KEY'),
  metaculusApiKey: value('METACULUS_API_KEY'),
  mysql: {
    host: value('MYSQL_HOST', 'DB_HOST'),
    port: int('MYSQL_PORT', int('DB_PORT', 3306, 1, 65535), 1, 65535),
    user: value('MYSQL_USER', 'DB_USER'),
    password: value('MYSQL_PASSWORD', 'DB_PASSWORD'),
    database: value('MYSQL_DATABASE', 'DB_NAME')
  },
  adminRefreshKey: value('EVIDENCE_ADMIN_KEY')
};

export const providerState = () => ({
  FRED: Boolean(config.fredApiKey),
  ForecastAPI: Boolean(config.forecastApiKey),
  WindyConfiguredButNotUsedAsProductionEvidence: Boolean(config.windyApiKey),
  CopernicusPublic: true,
  MetaculusReferenceOnly: Boolean(config.metaculusApiKey),
  PointReferenceOnly: Boolean(config.pointApiKey)
});
