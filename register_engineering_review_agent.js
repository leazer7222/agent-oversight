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

async function registerEngineeringReviewAgent() {
  const companyId    = '1021c018-fe0e-4ae8-a972-7487521cc3d9'; // reformai
  const definitionId = '621e2f75-2857-4bf6-9753-81a621596018';
  const agentId      = 'e6229606-78b9-4fd7-9424-6a62eb574255';

  // ── 1. Upsert Agent Definition ──────────────────────────────────────────
  console.log('--- Registering Engineering Review Agent Definition ---');
  const { data: def, error: defError } = await supabase
    .from('agent_definitions')
    .upsert({
      id:              definitionId,
      name:            'engineering-review-agent',
      display_name:    'Engineering Review Agent',
      description:     'Staff-level engineering review agent that connects user feedback to code-level root causes and produces prioritized, evidence-based improvement recommendations.',
      capability_tags: ['code-review', 'engineering', 'quality', 'user-feedback', 'analysis'],
      instance_type:   'stateless',
      input_schema:    {
        type: 'object',
        properties: {
          repo:               { type: 'string', description: 'GitHub owner/repo (e.g. leazer7222/agent-oversight)' },
          scope:              { type: 'string', description: 'Optional subdirectory path to limit review' },
          feedback_folder_id: { type: 'string', description: 'GDrive folder ID containing feedback docs' },
          feedback_text:      { type: 'string', description: 'Inline feedback text (alternative to GDrive)' }
        },
        required: ['repo']
      },
      output_schema:   {
        type: 'object',
        properties: {
          status:        { type: 'string' },
          review:        { type: 'object' },
          files_reviewed: { type: 'array', items: { type: 'string' } },
          feedback_docs: { type: 'array', items: { type: 'string' } }
        }
      },
      config_schema:   {},
      version:         '1.0.0',
      source_path:     'agents/library/engineering-review-agent/agent.py'
    })
    .select();

  if (defError) {
    console.error('Error registering definition:', defError);
    return;
  }
  console.log('Definition registered:', def[0].id);

  // ── 2. Upsert Agent Instance ─────────────────────────────────────────────
  console.log('--- Registering Engineering Review Agent Instance ---');
  const { data: agent, error: agentError } = await supabase
    .from('agents')
    .upsert({
      id:            agentId,
      name:          'reformai.engineering-review-agent',
      company_id:    companyId,
      definition_id: definitionId,
      agent_type:    'worker',
      status:        'active',
      trigger_type:  'manual',
      depth:         3,
      tags:          ['engineering', 'code-review', 'quality', 'reformai'],
      config_overrides: {},
      metadata: {}
    })
    .select();

  if (agentError) {
    console.error('Error registering agent instance:', agentError);
    return;
  }
  console.log('Agent instance registered:', agent[0].id);
  console.log('\nDone! Engineering review agent is live in Supabase.');
}

registerEngineeringReviewAgent().catch(console.error);
