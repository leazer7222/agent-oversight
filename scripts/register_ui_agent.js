const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
const envPath = 'c:/Users/cjlea/AgentProjects/agent-oversight/.env.local';
if (fs.existsSync(envPath)) {
  fs.readFileSync(envPath, 'utf8').split('\n').forEach(line => {
    const [key, ...rest] = line.split('=');
    if (key && rest.length) env[key.trim()] = rest.join('=').trim();
  });
}

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

async function registerUIDesignAgent() {
  const companyId     = '1021c018-fe0e-4ae8-a972-7487521cc3d9';
  const definitionId  = '5927c32b-36f4-4e2b-8a8b-1e5f8f322e70';
  const agentId       = 'fd1e8b23-1d8c-4b5a-9e1a-c7a8b9c0d1e2'; // Stable UUID for instances

  // ── 1. Upsert Agent Definition ──────────────────────────────────────────
  console.log('--- Registering UI Design Agent Definition ---');
  const { data: def, error: defError } = await supabase
    .from('agent_definitions')
    .upsert({
      id:               definitionId,
      name:             'ui-design-agent',
      display_name:     'UI Design & Frontend Agent',
      description:      'Transforms marketing blueprints into high-fidelity ReformAI Next.js components.',
      capability_tags:  ['ui', 'ux', 'frontend', 'react', 'nextjs', 'tailwind', 'framer-motion'],
      instance_type:    'stateless',
      input_schema:     {},
      output_schema:    {},
      config_schema:    {},
      version:          '1.0.0',
      source_path:      'agents/library/ui-design-agent/agent.py'
    })
    .select();

  if (defError) {
    console.error('Error registering definition:', defError);
    return;
  }
  console.log('Definition registered:', def[0].id);

  // ── 2. Upsert Agent Instance ─────────────────────────────────────────────
  console.log('--- Registering UI Design Agent Instance ---');
  const { data: agent, error: agentError } = await supabase
    .from('agents')
    .upsert({
      id:               agentId,
      name:             'reformai.ui-design-agent',
      company_id:       companyId,
      definition_id:    definitionId,
      agent_type:       'worker',
      status:           'active',
      trigger_type:     'manual',
      depth:            4,
      tags:             ['ui', 'reformai'],
      config_overrides: {
        theme_preference: 'dark',
        component_library: 'tailwind'
      },
      metadata: {}
    })
    .select();

  if (agentError) {
    console.error('Error registering agent instance:', agentError);
    return;
  }
  console.log('Agent instance registered:', agent[0].id);
  console.log('\nDone! UI Design agent is live in Supabase.');
}

registerUIDesignAgent().catch(console.error);
