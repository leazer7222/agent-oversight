// Register ba-scoping-agent: definition (agent_definitions) + ReformAI instance (agents).
// Follows the marketing/ui registration convention and LESSONS_LEARNED:
//   - agent.json agent_id == agent_definitions.id (the reserved UUID 1232ef02...)
//   - agents.id is a separate instance UUID
//   - resolve company by exact name 'ReformAI', never LIMIT 1
//   - definition upserted before instance (FK definition_id)
//   - trigger_type 'manual' (constraint rejects 'orchestrator')
//   - status 'paused' + paused_reason: registered for catalog/telemetry, runtime not yet implemented.
//     Does NOT claim operational. agent.py does not exist; migrations 024/025 not applied.
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});
const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

const DEFINITION_ID = '1232ef02-e83e-437a-a4a3-50b61090cb86'; // reserved; == agent.json agent_id
const INSTANCE_ID   = '0cc9bf15-49a5-4667-9985-77c31877490b'; // fresh instance UUID

(async () => {
  // 0. Resolve ReformAI by name (never LIMIT 1)
  const { data: companies, error: cErr } = await supabase
    .from('companies').select('id,name').eq('name', 'ReformAI');
  if (cErr || !companies || companies.length !== 1) {
    console.error('Company resolution failed (expected exactly 1 ReformAI):', cErr || companies);
    process.exit(1);
  }
  const companyId = companies[0].id;
  console.log('ReformAI company_id:', companyId);

  // 1. Upsert agent_definitions (tenant-neutral library entry)
  const { data: def, error: defErr } = await supabase
    .from('agent_definitions')
    .upsert({
      id:            DEFINITION_ID,
      name:          'ba-scoping-agent',
      display_name:  'BA Scoping Agent',
      description:   'Converts a feature idea into a scope-ready brief by resolving Concepts against existing product knowledge and codebase reality, surfacing high-divergence forks as blocking Questions, and capturing human answers as durable Decisions. A scoping and decision-extraction agent - not a PRD generator in v1.',
      capability_tags: ['feature_scoping', 'requirements_engineering', 'decision_extraction', 'product_intelligence', 'graph_operations'],
      instance_type: 'stateless',
      input_schema:  { $ref: 'docs/schemas/ba-scoping-input.schema.json' },
      output_schema: { $ref: 'docs/schemas/product-graph.schema.json' },
      config_schema: {},
      version:       '1.0.0',
      source_path:   'agents/library/ba-scoping-agent/'
    })
    .select();
  if (defErr) { console.error('definition upsert error:', defErr); process.exit(1); }
  console.log('definition registered:', def[0].id, def[0].name);

  // 2. Upsert agents instance (ReformAI-scoped deployment)
  const { data: agent, error: aErr } = await supabase
    .from('agents')
    .upsert({
      id:             INSTANCE_ID,
      name:           'reformai.ba-scoping-agent',
      company_id:     companyId,
      definition_id:  DEFINITION_ID,
      agent_type:     'worker',
      parent_agent_id: null,            // standalone worker
      depth:          1,
      platform:       'python',
      trigger_type:   'manual',
      trigger_config: {},
      status:         'paused',
      paused_at:      new Date().toISOString(),
      paused_reason:  'Registered for catalog + telemetry. Runtime (agent.py) not yet implemented; not operationally active. Migrations 024/025 (product_graph, cbc_identity_registry) authored but NOT applied.',
      registered_at:  new Date().toISOString(),
      tags:           ['product-intelligence', 'reformai', 'ba'],
      config_overrides: {
        product_key: 'reformai-product',
        paired_agent: 'codebase-context-agent'
      },
      metadata: {
        runtime_status: 'documented_registered_not_active',
        runtime_implemented: false,
        documentation: {
          readme:           'agents/library/ba-scoping-agent/README.md',
          lessons:          'agents/library/ba-scoping-agent/LESSONS.md',
          docs_dir:         'agents/library/ba-scoping-agent/docs/',
          input_schema:     'docs/schemas/ba-scoping-input.schema.json',
          output_schema:    'docs/schemas/product-graph.schema.json',
          consumes_schema:  'docs/schemas/codebase-context.schema.json'
        },
        storage: {
          migrations: ['supabase/migrations/024_product_graph_phase1.sql', 'supabase/migrations/025_cbc_identity_registry.sql'],
          applied: false
        }
      }
    })
    .select();
  if (aErr) { console.error('instance upsert error:', aErr); process.exit(1); }
  console.log('instance registered:', agent[0].id, agent[0].name, '| status:', agent[0].status);

  // 3. Read back for confirmation
  const { data: confDef } = await supabase.from('agent_definitions')
    .select('id,name,display_name,version,source_path').eq('id', DEFINITION_ID);
  const { data: confInst } = await supabase.from('agents')
    .select('id,name,company_id,definition_id,agent_type,status,trigger_type,depth').eq('id', INSTANCE_ID);
  console.log('\n--- CONFIRMATION ---');
  console.log('definition:', JSON.stringify(confDef[0]));
  console.log('instance:  ', JSON.stringify(confInst[0]));
})().catch(e => { console.error(e); process.exit(1); });
