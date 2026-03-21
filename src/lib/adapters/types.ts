// Core agent identity
export type AgentId = string // UUID from Supabase agents table

export type AgentStatus = 'active' | 'paused' | 'retired'

export type AgentHierarchy =
  | 'orchestrator_global'
  | 'orchestrator_company'
  | 'orchestrator_project'
  | 'sub_agent'

export type Company = 'reformai' | 'afterglow' | 'personal'

// Agent record from the agents table
export interface Agent {
  id: AgentId
  name: string
  description: string | null
  hierarchy: AgentHierarchy
  company: Company | null
  project: string | null
  status: AgentStatus
  created_at: string
}

// Run lifecycle
export type RunStatus = 'started' | 'completed' | 'failed'

export interface AgentRun {
  id: string // UUID
  agent_id: AgentId
  status: RunStatus
  started_at: string
  completed_at: string | null
  tokens_in: number | null
  tokens_out: number | null
  cost_usd: number | null
  error: string | null
  metadata: Record<string, unknown> | null
}

// Ingest payload — what agents POST to /api/ingest
export interface IngestPayload {
  agent_id: AgentId
  event: 'run_started' | 'run_completed' | 'run_failed'
  run_id: string
  timestamp?: string
  tokens_in?: number
  tokens_out?: number
  cost_usd?: number
  error?: string
  metadata?: Record<string, unknown>
}

// Response from /api/ingest
export interface IngestResponse {
  ok: boolean
  run_id: string
}
