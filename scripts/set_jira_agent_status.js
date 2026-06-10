// Flip the jira-sprint-reporting-agent instance status.
// Usage: node scripts/set_jira_agent_status.js <active|paused>
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [k, ...r] = line.split('='); if (k && r.length) env[k.trim()] = r.join('=').trim();
});
const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);
const INSTANCE_ID = '5544edd7-fe39-4340-9063-f9f71aef85b9';
const status = process.argv[2];
if (!['active', 'paused'].includes(status)) { console.error('arg must be active|paused'); process.exit(1); }

(async () => {
  const { data: cur } = await supabase.from('agents').select('metadata').eq('id', INSTANCE_ID);
  const metadata = { ...(cur && cur[0] ? cur[0].metadata : {}) };
  const patch = { status };
  if (status === 'active') {
    patch.paused_at = null; patch.paused_reason = null;
    metadata.runtime_implemented = true;
    metadata.runtime_status = 'runtime_implemented_telemetry_live';
    metadata.runtime_entrypoint = 'agents/library/jira-sprint-reporting-agent/agent.py';
  } else {
    patch.paused_at = new Date().toISOString();
    patch.paused_reason = 'Reverted to paused.';
  }
  patch.metadata = metadata;
  const { data, error } = await supabase.from('agents').update(patch).eq('id', INSTANCE_ID)
    .select('id,name,status,metadata');
  if (error) { console.error('update error:', error); process.exit(1); }
  console.log('updated:', data[0].name, '| status:', data[0].status,
              '| runtime_implemented:', data[0].metadata.runtime_implemented);
})().catch(e => { console.error(e); process.exit(1); });
