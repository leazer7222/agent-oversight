// Register jira-sprint-reporting-agent: definition (agent_definitions) + ReformAI instance (agents).
// Follows the ba/marketing/ui registration convention and LESSONS_LEARNED:
//   - agent.json agent_id == agent_definitions.id (reserved DEFINITION_ID)
//   - agents.id is a separate instance UUID
//   - resolve company by exact name 'ReformAI', never LIMIT 1
//   - definition upserted before instance (FK definition_id)
//   - trigger_type 'manual' (constraint rejects 'orchestrator')
//   - status 'paused': capability is PROVEN (live Sprint 1/2 reports) but there is no packaged
//     telemetry-emitting runtime yet. Honest catalog/identity registration, not "operational".
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
  const [key, ...rest] = line.split('=');
  if (key && rest.length) env[key.trim()] = rest.join('=').trim();
});
const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

const DEFINITION_ID = '04c82526-fa49-4241-9bbf-674a0a64108a'; // == agent.json agent_id
const INSTANCE_ID   = '5544edd7-fe39-4340-9063-f9f71aef85b9'; // fresh instance UUID

const DESCRIPTION = 'Pulls a completed sprint, its retrospective, and the upcoming sprint from Jira and Confluence, and assembles two artifacts: a comprehensive internal Sprint Review Analysis (Confluence page) and a distilled, brand-styled Management Report (PDF). Read-only on Jira except a human-gated t-shirt-size write-back; writes Confluence pages only. First capability of the ReformAI Jira Agent.';

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
      name:          'jira-sprint-reporting-agent',
      display_name:  'Jira Sprint Reporting Agent',
      description:   DESCRIPTION,
      capability_tags: ['sprint_reporting', 'agile_metrics', 'jira_integration', 'confluence_authoring', 'sprint_planning', 'management_reporting'],
      instance_type: 'stateless',
      input_schema:  { sources: ['jira:closed_sprint', 'confluence:retro_page', 'jira:future_sprint'] },
      output_schema: { artifacts: ['confluence:sprint_review_analysis', 'confluence:sprint_planning', 'pdf:management_report'] },
      config_schema: {},
      version:       '1.0.0',
      source_path:   'agents/library/jira-sprint-reporting-agent/'
    })
    .select();
  if (defErr) { console.error('definition upsert error:', defErr); process.exit(1); }
  console.log('definition registered:', def[0].id, def[0].name);

  // 2. Upsert agents instance (ReformAI-scoped deployment)
  const { data: agent, error: aErr } = await supabase
    .from('agents')
    .upsert({
      id:             INSTANCE_ID,
      name:           'reformai.jira-sprint-reporting-agent',
      company_id:     companyId,
      definition_id:  DEFINITION_ID,
      agent_type:     'worker',
      parent_agent_id: null,
      depth:          1,
      platform:       'python',
      trigger_type:   'manual',
      trigger_config: {},
      status:         'paused',
      paused_at:      new Date().toISOString(),
      paused_reason:  'Capability proven and live (Sprint 1 Review + Sprint 2 Planning published to Confluence RAPD; brand management PDF rendered). Currently driven interactively via the Atlassian MCP; no packaged autonomous runtime emitting run_started/run_completed telemetry yet. Registered for catalog/identity. Flip to active when the telemetry runtime is built.',
      registered_at:  new Date().toISOString(),
      tags:           ['jira', 'reformai', 'sprint-reporting', 'agile'],
      config_overrides: {
        atlassian_cloud_id: '6c97a9a2-291e-4c35-89da-b7c3d245e386',
        jira_project: 'RAI',
        jira_board_id: 3,
        confluence_space: 'RAPD'
      },
      metadata: {
        runtime_status: 'capability_proven_runtime_pending',
        runtime_implemented: false,
        design_spec: 'docs/agent-jira-sprint-reporting.md',
        documentation: {
          readme:  'agents/library/jira-sprint-reporting-agent/README.md',
          lessons: 'agents/library/jira-sprint-reporting-agent/LESSONS.md',
          agent_json: 'agents/library/jira-sprint-reporting-agent/agent.json'
        },
        live_artifacts: {
          sprint_1_review: 'confluence:166723587',
          sprint_2_planning: 'confluence:166985730',
          management_pdf: 'reports/sprint-1-review.pdf'
        },
        write_boundary: 'Can set issue fields (e.g. t-shirt size, human-gated) but cannot move issues between/out of sprints (Agile board API not exposed).'
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
