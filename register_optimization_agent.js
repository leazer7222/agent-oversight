const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

async function registerOptimizationAgent() {
  const companyId    = '1021c018-fe0e-4ae8-a972-7487521cc3d9';
  const definitionId = 'c3e7f2a1-9b4d-4e8f-a012-3456789abcde';
  const agentId      = '1ba970fb-caba-4c4d-9e91-0f07135c1a70';

  // ── 1. Upsert Agent Definition ──────────────────────────────────────────
  console.log('--- Registering Optimization Agent Definition ---');
  const { data: def, error: defError } = await supabase
    .from('agent_definitions')
    .upsert({
      id:              definitionId,
      name:            'optimization-agent',
      display_name:    'Agent Standards Optimization Agent',
      description:     'Scans agent library for standards compliance, code quality issues, and structural gaps, then synthesizes a prioritized improvement report via LLM.',
      capability_tags: ['audit', 'optimization', 'standards', 'quality'],
      instance_type:   'stateless',
      input_schema:    { repo_root: 'string (optional)' },
      output_schema:   { summary: 'string', agents: 'array', recommendations: 'string' },
      config_schema:   {},
      version:         '1.0.0',
      source_path:     'agents/library/optimization-agent/agent.py'
    })
    .select();

  if (defError) {
    console.error('Error registering definition:', defError);
    return;
  }
  console.log('Definition registered:', def[0].id);

  // ── 2. Upsert Agent Instance ─────────────────────────────────────────────
  console.log('--- Registering Optimization Agent Instance ---');
  const { data: agent, error: agentError } = await supabase
    .from('agents')
    .upsert({
      id:              agentId,
      name:            'reformai.optimization-agent',
      company_id:      companyId,
      definition_id:   definitionId,
      agent_type:      'worker',
      status:          'active',
      trigger_type:    'manual',
      depth:           2,
      tags:            ['optimization', 'audit', 'reformai'],
      config_overrides: {},
      metadata:        {}
    })
    .select();

  if (agentError) {
    console.error('Error registering agent instance:', agentError);
    return;
  }
  console.log('Agent instance registered:', agent[0].id);
  console.log('\nDone! Optimization agent is live in Supabase.');
}

registerOptimizationAgent().catch(console.error);
