import fs from 'node:fs';

const required = [
  'server.js',
  'src/config.js',
  'public/index.html',
  'public/providence-v15.css',
  'public/providence-v15-compat.css',
  'public/providence-v15-shell.js',
  'public/overview-v15.js',
  'public/predictions/index.html',
  'public/predictions/predictions-v15.js'
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
  version: '1.15.0'
}));
