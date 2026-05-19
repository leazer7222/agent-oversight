// Cost Intelligence — shared types
// RFC references: RFC-002, RFC-003, RFC-005

// ---------------------------------------------------------------------------
// Estimation feature vector (RFC-002 §10.1.1)
// Captured at dispatch time. Stored verbatim in estimate_artifacts.estimation_features_snapshot.
// Field names are frozen — changes require a feature_schema_version bump.
// ---------------------------------------------------------------------------

export interface EstimationFeatures {
  feature_schema_version:       string    // 'features-v1'
  captured_at:                  string    // ISO 8601
  prompt_chars:                 number
  context_ref_count:            number
  artifact_ref_count:           number
  tools_enabled:                string[]
  tools_definition_hash:        string
  system_prompt_hash:           string
  declared_max_steps:           number
  declared_child_runs:          number
  task_type_code:               string
  task_complexity_bucket:       string    // 'simple' | 'medium' | 'complex'
  context_window_requested_pct: number
}

// ---------------------------------------------------------------------------
// Pricing data from pricing_table_versions.entries[]
// ---------------------------------------------------------------------------

export interface ModelRates {
  input_per_1k_tokens_usd:        number
  output_per_1k_tokens_usd:       number
  cached_input_per_1k_tokens_usd: number
  reasoning_per_1k_tokens_usd:    number
  tool_call_per_invocation_usd:   number
}

export interface PricingEntry {
  provider: string
  model:    string
  rates:    ModelRates
}

export interface PricingSnapshot {
  provider:    string
  model:       string
  rates:       ModelRates
  captured_at: string
}

// ---------------------------------------------------------------------------
// Estimate result — returned by the deterministic estimator
// Directly maps to estimate_artifacts row fields
// ---------------------------------------------------------------------------

export interface EstimateResult {
  cost_p50_usd:              number
  cost_p75_usd:              number
  cost_p95_usd:              number
  tokens_in_p50:             number
  tokens_out_p50:            number
  estimated_latency_ms_p50:  number
  confidence:                'very_low' | 'low' | 'medium' | 'high' | 'very_high'
  estimation_tier:           'deterministic' | 'embedded_fallback'
  pricing_table_version_id:  string
  pricing_snapshot:          PricingSnapshot
  warnings:                  string[]
}
