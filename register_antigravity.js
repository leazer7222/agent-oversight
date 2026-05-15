const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
if (fs.existsSync('.env.local')) {
  fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
    const [key, ...rest] = line.split('=');
    if (key && rest.length) env[key.trim()] = rest.join('=').trim();
  });
}

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

async function registerAntigravity() {
  const companyId     = '87fb6e0d-ebff-4344-9b75-07c1a1a213ac'; // Personal
  const definitionId  = '9a8b7c6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d';
  const agentId       = '0f1e2d3c-4b5a-4a9b-8c7d-6e5f4d3c2b1a';

  console.log('--- Registering Antigravity Agent Definition ---');
  const { data: def, error: defError } = await supabase
    .from('agent_definitions')
    .upsert({
      id:               definitionId,
      name:             'antigravity',
      display_name:     'Antigravity Coding Assistant',
      description:      'Advanced agentic AI coding assistant powered by Gemini.',
      capability_tags:  ['coding', 'architecture', 'pair-programming', 'agentic-reasoning'],
      instance_type:    'stateless',
      default_model:    'gemini-3.1-pro',
      input_schema:     {},
      output_schema:    {},
      config_schema:    {},
      version:          '1.0.0',
      source_path:      'n/a'
    })
    .select();

  if (defError) {
    console.error('Error registering definition:', defError);
    return;
  }
  console.log('Definition registered:', def[0].id);

  console.log('--- Registering Antigravity Agent Instance ---');
  const { data: agent, error: agentError } = await supabase
    .from('agents')
    .upsert({
      id:               agentId,
      name:             'personal.antigravity',
      company_id:       companyId,
      definition_id:    definitionId,
      agent_type:       'worker',
      status:           'active',
      trigger_type:     'manual',
      depth:            1,
      tags:             ['coding', 'personal'],
      config_overrides: {},
      metadata: {
        platform: 'Antigravity Shell',
        role: 'Assistant'
      }
    })
    .select();

  if (agentError) {
    console.error('Error registering agent instance:', agentError);
    return;
  }
  console.log('Agent instance registered:', agent[0].id);
  console.log('\nDone! Antigravity is live in Supabase.');
}

registerAntigravity().catch(console.error);
