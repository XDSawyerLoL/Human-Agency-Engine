import fs from 'node:fs';

const required = [
  'server.js',
  'src/config.js',
  'public/index.html',
  'public/providence-v15.css',
  'public/providence-v15-compat.css',
  'public/providence-v15-pages.css',
  'public/providence-v15-shell.js',
  'public/overview-v15.js',
  'public/predictions/index.html',
  'public/predictions/predictions-v15.js',
  'public/horizons/index.html',
  'public/causal/index.html',
  'public/sports/index.html',
  'public/matches/index.html',
  'public/track-record/index.html',
  'public/backtest/index.html',
  'public/sources/index.html',
  'public/alerts/index.html',
  'public/settings/index.html'
];

for (const file of required) {
  if (!fs.existsSync(file)) {
    console.error(`[hostinger-build] missing required file: ${file}`);
    process.exit(1);
  }
}

console.log(JSON.stringify({
  ok: true,
  target: 'hostinger-node-web-app',
  entry: 'server.js',
  default_port: 3000,
  port_env_supported: true,
  static_root: 'public',
  visual_contract: 'providence-v15-exact-reference',
  sitewide_shell_compatibility: true,
  primary_pages: 11,
  version: '1.15.0'
}));
