// Core agent identity
export type AgentId = string // UUID from Supabase agents table

export type AgentStatus = 'active' | 'paused' | 'retired'

// Agent record from the agents table — field names match live DB columns exactly.
// Note: description lives in agent_definitions, not agents.
// Note: agent_type is the live column (not hierarchy); company_id is UUID (not Company slug).
export interface Agent {
  id:                  AgentId
  name:                string
  company_id:          string | null   // UUID FK to companies.id
  project_id:          string | null   // UUID FK to projects.id
  definition_id:       string | null   // UUID FK to agent_definitions.id
  agent_type:          string | null   // e.g. 'orchestrator', 'worker'
  parent_agent_id:     string | null
  depth:               number | null
  platform:            string | null
  model:               string | null
  trigger_type:        string | null
  trigger_config:      Record<string, unknown> | null
  status:              string | null
  cost_limit_usd:      number | null
  cost_limit_period:   string | null
  max_errors_per_hour: number | null
  priority:            number | null
  tags:                string[] | null
  can_trigger:         string[] | null
  can_be_triggered_by: string[] | null
  config_overrides:    Record<string, unknown> | null
  registered_at:       string | null
  last_run_at:         string | null
  paused_at:           string | null
  paused_reason:       string | null
  metadata:            Record<string, unknown> | null
}

// Run lifecycle
export type RunStatus = 'started' | 'completed' | 'failed'

export interface AgentRun {
  id:            string   // UUID
  agent_id:      AgentId
  status:        RunStatus
  started_at:    string
  created_at:    string
  completed_at:  string | null
  timeout_at:    string | null   // zombie detection threshold
  parent_run_id: string | null   // retry chain linkage
  tokens_in:     number | null
  tokens_out:    number | null
  cost_usd:      number | null
  cost_reported: boolean         // false = cost_usd was never sent; true = explicitly reported
  error:         string | null
  metadata:      Record<string, unknown> | null
}

// Ingest payload — what agents POST to /api/ingest
export interface IngestPayload {
  agent_id:      AgentId
  event:         'run_started' | 'run_completed' | 'run_failed'
  run_id:        string
  timestamp?:    string
  tokens_in?:    number
  tokens_out?:   number
  cost_usd?:     number
  error?:        string
  metadata?:     Record<string, unknown>
  parent_run_id?: string  // set on retries to link to original run
  step_name?:    string   // optional label shown in agent_events message
}

// Response from /api/ingest
export interface IngestResponse {
  ok: boolean
  run_id: string
}
