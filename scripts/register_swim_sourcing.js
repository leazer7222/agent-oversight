#!/usr/bin/env node
/**
 * Register Cameron's swim-school tenant and its agents in Agent Oversight.
 *
 * Mirrors scripts/register_ba_scoping_agent.js. Idempotent: re-running matches
 * existing rows by name instead of creating duplicates.
 *
 *   node scripts/register_swim_sourcing.js --dry-run     # print the plan only
 *   node scripts/register_swim_sourcing.js               # write
 *
 * TEMPORARY IDENTIFIER. Cameron's legal company name and domain are not
 * confirmed, so the company is registered as 'swim-school-tbd'. Nothing here
 * invents a business name, address or domain - those arrive from her later and
 * are a rename, not a re-registration.
 *
 * Agents are registered with status='paused' deliberately. /api/ingest returns
 * 403 for a non-active agent and the worker's preflight refuses to run one, so
 * a fresh registration cannot execute or spend anything until someone flips it
 * on after a smoke test.
 */

const { createClient } = require('@supabase/supabase-js')
const fs = require('fs')
const path = require('path')

function loadEnv() {
  // .env.local lives in the main checkout; this script may run from a worktree.
  let dir = __dirname
  for (let i = 0; i < 6; i++) {
    const candidate = path.join(dir, '.env.local')
    if (fs.existsSync(candidate)) {
      for (const line of fs.readFileSync(candidate, 'utf8').split('\n')) {
        const trimmed = line.trim()
        if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue
        const idx = trimmed.indexOf('=')
        const key = trimmed.slice(0, idx).trim()
        const val = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, '')
        if (!process.env[key]) process.env[key] = val
      }
      return
    }
    dir = path.dirname(dir)
  }
}
loadEnv()

const DRY_RUN = process.argv.includes('--dry-run')

const COMPANY = {
  name: 'swim-school-tbd',
  slug: 'swim-school-tbd',
  description:
    'Swim school (Katy, TX). Temporary identifier - legal name and domain pending ' +
    'confirmation by the owner.',
  // A real ceiling from day one. The platform previously had cost_limit_usd NULL
  // on every company, so the spend cap was both unenforced AND unpopulated.
  cost_limit_usd: 25,
  cost_limit_period: 'monthly',
}

const PROJECT = { name: 'facility-sourcing', description: 'Pool facility discovery, qualification and outreach' }

// Definitions are tenant-neutral (shared capability library); instances are
// tenant-scoped and named {tenant}.{capability}, per the convention in
// LESSONS_LEARNED.
const DEFINITIONS = [
  {
    name: 'facility-discovery-agent',
    display_name: 'Facility Discovery Agent',
    description:
      'Finds candidate facilities via a places/search API within a configurable radius. ' +
      'Never invents a facility: every row carries a stable source id and fetch timestamp.',
    capability_tags: ['discovery', 'prospecting', 'places-api'],
    instance_type: 'stateless',
    default_model: null,
    source_path: 'agents/library/facility-discovery-agent/discovery.py',
    version: '1.0.0',
  },
  {
    name: 'facility-qualification-agent',
    display_name: 'Facility Qualification Agent',
    description:
      'Deterministic weighted scoring of a facility against configurable criteria. ' +
      'Distinguishes verified, inferred and unknown; unknown is never scored as a guess.',
    capability_tags: ['qualification', 'scoring', 'deterministic'],
    instance_type: 'stateless',
    default_model: null,
    source_path: 'agents/library/facility-qualification-agent/scoring.py',
    version: '1.0.0',
  },
  {
    name: 'outreach-agent',
    display_name: 'Outreach Agent',
    description:
      'Drafts personalised outreach and sends only what an authenticated human approved, ' +
      'bound by content hash. Enforces suppression, daily caps and exactly-once delivery.',
    capability_tags: ['outreach', 'email', 'human-in-the-loop'],
    instance_type: 'stateless',
    default_model: 'claude-sonnet-4-6',
    source_path: 'agents/library/outreach-agent/',
    version: '1.0.0',
  },
  {
    name: 'reply-triage-agent',
    display_name: 'Reply Triage Agent',
    description:
      'Classifies inbound replies and proposes next actions. Treats inbound email as ' +
      'untrusted data; commercial topics escalate to the owner by deterministic rule.',
    capability_tags: ['classification', 'inbox', 'safety'],
    instance_type: 'stateless',
    default_model: 'claude-sonnet-4-6',
    source_path: 'agents/library/outreach-agent/safety.py',
    version: '1.0.0',
  },
]

const ORCHESTRATOR = {
  name: 'swim-sourcing-orchestrator',
  display_name: 'Swim Sourcing Orchestrator',
  description: 'Sequences discovery, qualification, outreach, reply handling and scheduling. Makes no LLM calls.',
  capability_tags: ['orchestrator', 'lifecycle'],
  instance_type: 'stateless',
  source_path: 'agents/teams/swim-sourcing/worker.py',
  version: '1.0.0',
}

async function main() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) {
    console.error('[register] NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required')
    process.exit(2)
  }
  // service_role is ~219 chars; the anon key is ~105. Confusing them is a
  // documented past failure, so check rather than discover it via a 401.
  if (key.length < 150 && !key.startsWith('sb_secret')) {
    console.error(`[register] SUPABASE_SERVICE_ROLE_KEY looks wrong (${key.length} chars). ` +
      'The anon key will not work for registration.')
    process.exit(2)
  }

  const sb = createClient(url, key, { auth: { persistSession: false } })

  if (DRY_RUN) {
    console.log('[register] DRY RUN - nothing will be written\n')
    console.log('company:      ', COMPANY.name, `(cap $${COMPANY.cost_limit_usd}/${COMPANY.cost_limit_period})`)
    console.log('project:      ', PROJECT.name)
    console.log('orchestrator: ', `swimschool.${ORCHESTRATOR.name}`)
    for (const d of DEFINITIONS) console.log('worker:       ', `swimschool.${d.name}`)
    console.log('\nAll agent instances will be created with status=paused.')
    return
  }

  // --- company ------------------------------------------------------------
  let { data: company } = await sb.from('companies').select('id, name')
    .eq('name', COMPANY.name).maybeSingle()
  if (!company) {
    const ins = await sb.from('companies').insert(COMPANY).select('id, name').single()
    if (ins.error) throw new Error(`company insert failed: ${ins.error.message}`)
    company = ins.data
    console.log(`[register] created company ${company.name} (${company.id})`)
  } else {
    console.log(`[register] company exists: ${company.name} (${company.id})`)
  }

  // --- project ------------------------------------------------------------
  let { data: project } = await sb.from('projects').select('id, name')
    .eq('name', PROJECT.name).eq('company_id', company.id).maybeSingle()
  if (!project) {
    const ins = await sb.from('projects')
      .insert({ ...PROJECT, company_id: company.id, status: 'active' })
      .select('id, name').single()
    if (ins.error) throw new Error(`project insert failed: ${ins.error.message}`)
    project = ins.data
    console.log(`[register] created project ${project.name} (${project.id})`)
  } else {
    console.log(`[register] project exists: ${project.name} (${project.id})`)
  }

  // --- definitions --------------------------------------------------------
  const defIds = {}
  for (const def of [ORCHESTRATOR, ...DEFINITIONS]) {
    let { data: row } = await sb.from('agent_definitions').select('id, name')
      .eq('name', def.name).maybeSingle()
    if (!row) {
      const ins = await sb.from('agent_definitions').insert(def).select('id, name').single()
      if (ins.error) throw new Error(`definition ${def.name} failed: ${ins.error.message}`)
      row = ins.data
      console.log(`[register] created definition ${row.name} (${row.id})`)
    } else {
      console.log(`[register] definition exists: ${row.name} (${row.id})`)
    }
    defIds[def.name] = row.id
  }

  // --- orchestrator instance FIRST (workers reference it via parent_agent_id)
  const orchName = `swimschool.${ORCHESTRATOR.name}`
  let { data: orch } = await sb.from('agents').select('id, name')
    .eq('name', orchName).maybeSingle()
  if (!orch) {
    const ins = await sb.from('agents').insert({
      name: orchName,
      company_id: company.id,
      project_id: project.id,
      definition_id: defIds[ORCHESTRATOR.name],
      agent_type: 'orchestrator',
      depth: 0,
      platform: 'python',
      // 'orchestrator' is NOT an accepted trigger_type value - the CHECK
      // constraint rejects it. 'manual' is correct for script/CLI invocation.
      trigger_type: 'manual',
      status: 'paused',
      paused_reason: 'awaiting smoke test and tenant credential',
      cost_limit_usd: COMPANY.cost_limit_usd,
      cost_limit_period: COMPANY.cost_limit_period,
      tags: ['swim-sourcing', 'orchestrator'],
      metadata: { runtime_implemented: true, schema: 'swim_sourcing' },
    }).select('id, name').single()
    if (ins.error) throw new Error(`orchestrator insert failed: ${ins.error.message}`)
    orch = ins.data
    console.log(`[register] created orchestrator ${orch.name} (${orch.id})`)
  } else {
    console.log(`[register] orchestrator exists: ${orch.name} (${orch.id})`)
  }

  // --- worker instances ---------------------------------------------------
  for (const def of DEFINITIONS) {
    const instName = `swimschool.${def.name}`
    const { data: existing } = await sb.from('agents').select('id, name')
      .eq('name', instName).maybeSingle()
    if (existing) {
      console.log(`[register] agent exists: ${existing.name} (${existing.id})`)
      continue
    }
    const ins = await sb.from('agents').insert({
      name: instName,
      company_id: company.id,
      project_id: project.id,
      definition_id: defIds[def.name],
      agent_type: 'worker',
      parent_agent_id: orch.id,
      depth: 1,
      platform: 'python',
      model: def.default_model,
      trigger_type: 'manual',
      status: 'paused',
      paused_reason: 'awaiting smoke test and tenant credential',
      cost_limit_usd: COMPANY.cost_limit_usd,
      cost_limit_period: COMPANY.cost_limit_period,
      tags: ['swim-sourcing'],
      metadata: { runtime_implemented: true, schema: 'swim_sourcing' },
    }).select('id, name').single()
    if (ins.error) throw new Error(`agent ${instName} failed: ${ins.error.message}`)
    console.log(`[register] created agent ${ins.data.name} (${ins.data.id})`)
  }

  console.log('\n[register] done. All agents are PAUSED.')
  console.log('[register] next: store Cameron\'s Anthropic key, smoke test, then activate.')
}

main().catch((err) => {
  console.error(`[register] FAILED: ${err.message}`)
  process.exit(1)
})
