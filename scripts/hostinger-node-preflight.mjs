import fs from 'node:fs';

const required = [
  'server.js',
  'src/config.js',
  'public/index.html',
  'public/providence-v14.css',
  'public/providence-v14-shell.js',
  'public/predictions/index.html',
  'public/predictions/predictions-v14-3.js',
  'public/predictions/predictions-v14-3.css'
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
  version: '1.14.3'
}));
