// Register codebase-context-agent: definition (agent_definitions) + ReformAI instance (agents).
// Follows register_ba_scoping_agent.js and LESSONS_LEARNED:
//   - agent.json agent_id == agent_definitions.id (reserved UUID 93b45e81...)
//   - agents.id is a separate instance UUID
//   - resolve company by exact name 'ReformAI', never LIMIT 1
//   - definition upserted before instance (FK definition_id)
//   - trigger_type 'manual' (constraint rejects 'orchestrator')
//   - status 'paused' + paused_reason: registered for catalog/telemetry, runtime not yet implemented.
//     Does NOT claim operational. agent.py does not exist; migration 025 not applied.
//     metadata.runtime_implemented = false.
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});
const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

const DEFINITION_ID = '93b45e81-a1e5-47d8-98b1-0575de49a21b'; // reserved; == agent.json agent_id
const INSTANCE_ID   = 'b118d9e1-c3ff-49c3-bb8b-f3c1bb985d2a'; // fresh instance UUID

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
      name:          'codebase-context-agent',
      display_name:  'Codebase Context Agent',
      description:   'Analyzes an external target codebase read-only at a pinned commit and produces a structured codebase-context.json artifact describing code reality (entities, actors, capabilities, domain signals, glossary, coverage, evidence) for downstream BA scoping. Describes WHAT IS; never scopes WHAT SHOULD BE. Owns the cbc:* identity registry.',
      capability_tags: ['codebase_analysis', 'code_intelligence', 'static_analysis', 'identity_registry', 'context_extraction'],
      instance_type: 'stateless',
      input_schema:  { $ref: 'agents/library/codebase-context-agent/docs/input-contract.md' },
      output_schema: { $ref: 'docs/schemas/codebase-context.schema.json' },
      config_schema: {},
      version:       '1.0.0',
      source_path:   'agents/library/codebase-context-agent/'
    })
    .select();
  if (defErr) { console.error('definition upsert error:', defErr); process.exit(1); }
  console.log('definition registered:', def[0].id, def[0].name);

  // 2. Upsert agents instance (ReformAI-scoped deployment)
  const { data: agent, error: aErr } = await supabase
    .from('agents')
    .upsert({
      id:             INSTANCE_ID,
      name:           'reformai.codebase-context-agent',
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
      paused_reason:  'Registered for catalog + telemetry. Runtime (agent.py) not yet implemented; not operationally active. Migration 025 (cbc_identity_registry) authored but NOT applied.',
      registered_at:  new Date().toISOString(),
      tags:           ['product-intelligence', 'reformai', 'cca', 'codebase-context'],
      config_overrides: {
        product_key: 'reformai-product',
        paired_agent: 'ba-scoping-agent'
      },
      metadata: {
        runtime_status: 'documented_registered_not_active',
        runtime_implemented: false,
        owns_identifiers: ['cbc:*', 'cbc_identity_registry', 'cbc_registry_events'],
        never_owns: ['CON-*', 'FEAT-*', 'QST-*', 'DEC-*', 'Rule', 'Attribute', 'PRD', 'user-stories', 'acceptance-criteria', 'product-recommendations'],
        documentation: {
          readme:           'agents/library/codebase-context-agent/README.md',
          lessons:          'agents/library/codebase-context-agent/LESSONS.md',
          docs_dir:         'agents/library/codebase-context-agent/docs/',
          input_contract:   'agents/library/codebase-context-agent/docs/input-contract.md',
          output_schema:    'docs/schemas/codebase-context.schema.json'
        },
        storage: {
          migrations: ['supabase/migrations/025_cbc_identity_registry.sql'],
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
