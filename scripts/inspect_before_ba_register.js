// Read-only pre-flight inspection before registering ba-scoping-agent.
// DB-first inspection per LESSONS_LEARNED. Makes no writes.
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});
const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

const DEF_ID = '1232ef02-e83e-437a-a4a3-50b61090cb86';

(async () => {
  // 1. Resolve ReformAI company by name (never LIMIT 1)
  const { data: companies, error: cErr } = await supabase
    .from('companies').select('id,name').eq('name', 'ReformAI');
  console.log('ReformAI companies by name:', cErr || companies);

  // 2. Distinct status values currently in use (informs the allowed set)
  const { data: agents, error: aErr } = await supabase
    .from('agents').select('name,status,agent_type,depth');
  if (aErr) console.log('agents read error:', aErr);
  else {
    const statuses = [...new Set(agents.map(a => a.status))];
    console.log('distinct agent.status in use:', statuses);
    console.log('agent count:', agents.length);
  }

  // 3. Does our definition or instance already exist?
  const { data: defExisting } = await supabase
    .from('agent_definitions').select('id,name').eq('id', DEF_ID);
  console.log('definition 1232ef02 existing:', defExisting);
  const { data: instExisting } = await supabase
    .from('agents').select('id,name').eq('name', 'reformai.ba-scoping-agent');
  console.log('instance reformai.ba-scoping-agent existing:', instExisting);
})().catch(console.error);
