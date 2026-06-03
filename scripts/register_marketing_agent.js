const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

// Verified column names from DB:
// agent_definitions: id, name, display_name, description, capability_tags, instance_type, default_model, input_schema, output_schema, config_schema, version, source_path
// agents: id, name, company_id, definition_id, agent_type, depth, trigger_type, trigger_config, status, config_overrides, metadata, tags

async function registerMarketingAgent() {
  const companyId     = '1021c018-fe0e-4ae8-a972-7487521cc3d9';
  const definitionId  = '8482d8c3-1811-4712-881b-537449339e31';
  const agentId       = '761c56f6-4de8-4859-974a-43d964de62f0';

  // ── 1. Upsert Agent Definition ──────────────────────────────────────────
  console.log('--- Registering Marketing Agent Definition ---');
  const { data: def, error: defError } = await supabase
    .from('agent_definitions')
    .upsert({
      id:               definitionId,
      name:             'marketing-agent',
      display_name:     'Marketing Strategy Executive Agent',
      description:      'Senior marketing executive agent for ReformAI. Produces landing page blueprints.',
      capability_tags:  ['marketing', 'strategy', 'positioning', 'ui-handoff'],
      instance_type:    'stateless',
      input_schema:     {},
      output_schema:    {},
      config_schema:    {},
      version:          '1.0.0',
      source_path:      'agents/library/marketing-agent/agent.py'
    })
    .select();

  if (defError) {
    console.error('Error registering definition:', defError);
    return;
  }
  console.log('Definition registered:', def[0].id);

  // ── 2. Upsert Agent Instance ─────────────────────────────────────────────
  console.log('--- Registering Marketing Agent Instance ---');
  const { data: agent, error: agentError } = await supabase
    .from('agents')
    .upsert({
      id:               agentId,
      name:             'reformai.marketing-agent',
      company_id:       companyId,
      definition_id:    definitionId,
      agent_type:       'worker',
      status:           'active',
      trigger_type:     'manual',
      depth:            3,
      tags:             ['marketing', 'reformai'],
      config_overrides: {
        default_goal: 'Optimize landing pages for homeowner conversion',
        target_segments: ['homeowners', 'service_providers', 'home_sellers']
      },
      metadata: {}
    })
    .select();

  if (agentError) {
    console.error('Error registering agent instance:', agentError);
    return;
  }
  console.log('Agent instance registered:', agent[0].id);
  console.log('\nDone! Marketing agent is live in Supabase.');
}

registerMarketingAgent().catch(console.error);
