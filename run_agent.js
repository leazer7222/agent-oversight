const { spawnSync } = require('child_process');
const fs = require('fs');
const env = { ...process.env };
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});
const result = spawnSync('python', ['agents/library/marketing-agent/agent.py'], { env, stdio: 'inherit' });
process.exit(result.status || 0);
