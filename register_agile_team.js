const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

// Stable IDs — never change these
const IDS = {
  companyId:               '1021c018-fe0e-4ae8-a972-7487521cc3d9', // reformai

  pcaDefinitionId:         'd4e5f6a7-b8c9-4234-8def-456789012345',
  pcaAgentId:              'a1b2c3d4-e5f6-7890-abcd-ef1234567890', // matches agent.json

  orchestratorDefinitionId: 'e5f6a7b8-c9d0-4345-9ef0-567890123456',
  orchestratorAgentId:      'b2c3d4e5-f6a7-8901-bcde-f12345678901',
};

async function register() {
  console.log('=== Registering Agile Team agents ===\n');

  // ── 1. Orchestrator Definition ───────────────────────────────────────────
  console.log('1. Registering Agile Team Orchestrator definition...');
  const { data: orchDef, error: orchDefErr } = await supabase
    .from('agent_definitions')
    .upsert({
      id:              IDS.orchestratorDefinitionId,
      name:            'agile-team-orchestrator',
      display_name:    'Agile Team Orchestrator',
      description:     'Deterministic workflow runner for the Agile Team. Enforces staleness gate, assembles context bundle, sequences specialist agents (PCA → SSA → EPA → QA), validates schema contracts, saves artifacts.',
      capability_tags: ['agile', 'orchestration', 'workflow', 'quality-gate'],
      instance_type:   'stateless',
      default_model:   null,
      input_schema:    {},
      output_schema:   {},
      config_schema:   {},
      version:         '1.0.0',
      source_path:     'agents/teams/agile/run.py',
    })
    .select();

  if (orchDefErr) { console.error('ERROR registering orchestrator definition:', orchDefErr); process.exit(1); }
  console.log('   ✓ Orchestrator definition:', orchDef[0].id);

  // ── 2. Orchestrator Agent Instance ──────────────────────────────────────
  console.log('2. Registering Agile Team Orchestrator instance...');
  const { data: orchAgent, error: orchAgentErr } = await supabase
    .from('agents')
    .upsert({
      id:             IDS.orchestratorAgentId,
      name:           'agile.orchestrator',
      company_id:     IDS.companyId,
      definition_id:  IDS.orchestratorDefinitionId,
      agent_type:     'orchestrator',
      depth:          1,
      status:         'active',
      trigger_type:   'manual',
      tags:           ['agile-team', 'orchestrator', 'agent-oversight'],
      config_overrides: {
        workspace_id:   'agent-oversight',
        team_id:        'agile',
      },
      metadata: {
        manages_agents: [IDS.pcaAgentId],
        phase:          1,
        note:           'Phase 1 — PCA only. SSA, EPA, QA added in later phases.',
      },
    })
    .select();

  if (orchAgentErr) { console.error('ERROR registering orchestrator agent:', orchAgentErr); process.exit(1); }
  console.log('   ✓ Orchestrator agent instance:', orchAgent[0].id);

  // ── 3. PCA Definition ───────────────────────────────────────────────────
  console.log('3. Registering PCA agent definition...');
  const { data: pcaDef, error: pcaDefErr } = await supabase
    .from('agent_definitions')
    .upsert({
      id:              IDS.pcaDefinitionId,
      name:            'product-clarification-agent',
      display_name:    'Product Clarification Agent',
      description:     'Converts fuzzy product goals into structured Clarification Briefs for the Agile Team. Reads workspace canonical docs (PRODUCT.md, DOMAIN.md, STORY-READY.md) and produces a Brief conforming to clarification-brief.schema.json.',
      capability_tags: ['agile', 'product-clarification', 'requirements', 'scope-definition'],
      instance_type:   'stateless',
      default_model:   'claude-sonnet-4-6',
      input_schema:    {},
      output_schema:   { schema_ref: 'docs/schemas/clarification-brief.schema.json' },
      config_schema:   {},
      version:         '1.0.0',
      source_path:     'agents/library/product-clarification-agent/agent.py',
    })
    .select();

  if (pcaDefErr) { console.error('ERROR registering PCA definition:', pcaDefErr); process.exit(1); }
  console.log('   ✓ PCA definition:', pcaDef[0].id);

  // ── 4. PCA Agent Instance ────────────────────────────────────────────────
  console.log('4. Registering PCA agent instance (agent-oversight workspace)...');
  const { data: pcaAgent, error: pcaAgentErr } = await supabase
    .from('agents')
    .upsert({
      id:             IDS.pcaAgentId,
      name:           'agile.product-clarification-agent',
      company_id:     IDS.companyId,
      definition_id:  IDS.pcaDefinitionId,
      agent_type:     'worker',
      parent_agent_id: IDS.orchestratorAgentId,
      depth:          2,
      status:         'active',
      trigger_type:   'manual',
      tags:           ['agile-team', 'pca', 'agent-oversight'],
      config_overrides: {
        workspace_id:    'agent-oversight',
        team_id:         'agile',
        context_bundle:  'agile-v1',
      },
      metadata: {
        schema_contract: 'clarification-brief.schema.json',
        mcp_dependencies: [],
      },
    })
    .select();

  if (pcaAgentErr) { console.error('ERROR registering PCA agent:', pcaAgentErr); process.exit(1); }
  console.log('   ✓ PCA agent instance:', pcaAgent[0].id);

  console.log('\n=== Registration complete ===\n');
  console.log('Agent IDs to add to .env.local:');
  console.log(`  PCA_AGENT_ID=${IDS.pcaAgentId}`);
  console.log(`  AGILE_ORCHESTRATOR_AGENT_ID=${IDS.orchestratorAgentId}`);
}

register().catch(err => { console.error(err); process.exit(1); });
