const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

async function registerAuditAgent() {
  const companyId    = '1021c018-fe0e-4ae8-a972-7487521cc3d9';
  const definitionId = 'a7c2e4f8-3b1d-4e9a-8f05-6789012bcdef';
  const agentId      = '5fdd7a16-153c-4e54-ac61-7ebe642a0dca';

  console.log('--- Registering Audit Agent Definition ---');
  const { data: def, error: defError } = await supabase
    .from('agent_definitions')
    .upsert({
      id:              definitionId,
      name:            'audit-agent',
      display_name:    'Context Quality Audit Agent',
      description:     'Evaluates context quality against a goal using LLM scoring; passes or fails based on relevance.',
      capability_tags: ['audit', 'quality', 'validation'],
      instance_type:   'stateless',
      input_schema:    { query: 'string', context: 'string' },
      output_schema:   { passed: 'boolean', score: 'integer', reasoning: 'string' },
      config_schema:   {},
      version:         '1.0.0',
      source_path:     'agents/library/audit-agent/agent.py'
    })
    .select();

  if (defError) { console.error('Error registering definition:', defError); return; }
  console.log('Definition registered:', def[0].id);

  console.log('--- Registering Audit Agent Instance ---');
  const { data: agent, error: agentError } = await supabase
    .from('agents')
    .upsert({
      id:              agentId,
      name:            'reformai.audit-agent',
      company_id:      companyId,
      definition_id:   definitionId,
      agent_type:      'worker',
      status:          'active',
      trigger_type:    'manual',
      depth:           2,
      tags:            ['audit', 'quality', 'reformai'],
      config_overrides: {},
      metadata:        {}
    })
    .select();

  if (agentError) { console.error('Error registering agent instance:', agentError); return; }
  console.log('Agent instance registered:', agent[0].id);
  console.log('\nDone! Audit agent is live in Supabase.');
}

registerAuditAgent().catch(console.error);
