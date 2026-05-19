-- Migration 013: Adaptive Cost Risk Engine — Phase 1 Group 1
--   pricing_table_versions  (ART-003, RFC-002 §10)
--   task_taxonomy_versions  (RFC-005 §3)
--   task_types              (RFC-005 §3, §4)
--   Seeds: pricing-2026-05 (10 models) + taxonomy-v1 (8 task types)
--
-- Depends on: 012_cost_risk_engine_phase0.sql
--   - platform schema must exist
--   - platform.apply_append_only_rls() function must exist
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002, RFC-005, RFC-009

-- ---------------------------------------------------------------------------
-- 1. cost_intelligence schema
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS cost_intelligence;

-- ---------------------------------------------------------------------------
-- 2. pricing_table_versions — ART-003 (RFC-002 §10)
--    Records per-token and per-tool-call cost for every provider/model pair.
--    Immutable after activation. One row is active at any time.
-- ---------------------------------------------------------------------------

CREATE TABLE cost_intelligence.pricing_table_versions (
  id              UUID        NOT NULL  DEFAULT gen_random_uuid(),
  version         TEXT        NOT NULL,
  status          TEXT        NOT NULL
                    CHECK (status IN ('draft', 'active', 'retired')),
  effective_from  TIMESTAMPTZ NOT NULL,
  effective_until TIMESTAMPTZ,
  entries         JSONB       NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL  DEFAULT now(),
  created_by      TEXT        NOT NULL,
  activated_at    TIMESTAMPTZ,
  activated_by    TEXT,
  retired_at      TIMESTAMPTZ,
  retired_by      TEXT,
  predecessor_id  UUID,
  PRIMARY KEY (id),
  UNIQUE (version)
);

ALTER TABLE cost_intelligence.pricing_table_versions
  ADD CONSTRAINT fk_pricing_predecessor
  FOREIGN KEY (predecessor_id)
  REFERENCES cost_intelligence.pricing_table_versions(id)
  ON DELETE RESTRICT;

-- Enforces at most one active pricing table (RFC-002 §10)
CREATE UNIQUE INDEX uq_one_active_pricing_table
  ON cost_intelligence.pricing_table_versions (status)
  WHERE status = 'active';

SELECT platform.apply_append_only_rls('cost_intelligence', 'pricing_table_versions');

-- ---------------------------------------------------------------------------
-- 3. task_taxonomy_versions — RFC-005 §3
--    Versioned container for the set of task type definitions.
--    One version is active at any time.
-- ---------------------------------------------------------------------------

CREATE TABLE cost_intelligence.task_taxonomy_versions (
  id                 UUID        NOT NULL  DEFAULT gen_random_uuid(),
  version            TEXT        NOT NULL,
  status             TEXT        NOT NULL
                       CHECK (status IN ('draft', 'active', 'deprecated')),
  classifier_version TEXT        NOT NULL,
  activated_at       TIMESTAMPTZ,
  deprecated_at      TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL  DEFAULT now(),
  created_by         TEXT        NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (version)
);

-- Enforces at most one active taxonomy (RFC-005 INV-TAX-004)
CREATE UNIQUE INDEX uq_one_active_taxonomy
  ON cost_intelligence.task_taxonomy_versions (status)
  WHERE status = 'active';

SELECT platform.apply_append_only_rls('cost_intelligence', 'task_taxonomy_versions');

-- ---------------------------------------------------------------------------
-- 4. task_types — RFC-005 §3
--    Individual task type definitions, each with a machine-implementable
--    complexity classifier (complexity_definition JSONB).
--    code is a stable machine identifier — never renamed (RFC-005 §2).
-- ---------------------------------------------------------------------------

CREATE TABLE cost_intelligence.task_types (
  id                    UUID        NOT NULL  DEFAULT gen_random_uuid(),
  taxonomy_version_id   UUID        NOT NULL,
  code                  TEXT        NOT NULL,
  label                 TEXT        NOT NULL,
  description           TEXT        NOT NULL,
  complexity_definition JSONB       NOT NULL,
  primary_use_cases     TEXT[]      NOT NULL  DEFAULT '{}',
  exclusions            TEXT[]      NOT NULL  DEFAULT '{}',
  superseded_by_id      UUID,
  min_calibration_runs  INTEGER     NOT NULL  DEFAULT 30,
  created_at            TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (taxonomy_version_id, code)
);

ALTER TABLE cost_intelligence.task_types
  ADD CONSTRAINT fk_task_types_taxonomy
  FOREIGN KEY (taxonomy_version_id)
  REFERENCES cost_intelligence.task_taxonomy_versions(id)
  ON DELETE RESTRICT;

ALTER TABLE cost_intelligence.task_types
  ADD CONSTRAINT fk_task_types_superseded_by
  FOREIGN KEY (superseded_by_id)
  REFERENCES cost_intelligence.task_types(id)
  ON DELETE RESTRICT;

SELECT platform.apply_append_only_rls('cost_intelligence', 'task_types');

-- ---------------------------------------------------------------------------
-- 5. Seed: pricing-2026-05 (active)
--    10 models across Anthropic, OpenAI, Google.
--    Rates are per 1,000 tokens (input/output/cached/reasoning) and per
--    tool call invocation. Source: provider pricing pages, May 2026.
--
--    entries schema per entry:
--      { provider, model, rates: {
--          input_per_1k_tokens_usd, output_per_1k_tokens_usd,
--          cached_input_per_1k_tokens_usd, reasoning_per_1k_tokens_usd,
--          tool_call_per_invocation_usd } }
-- ---------------------------------------------------------------------------

INSERT INTO cost_intelligence.pricing_table_versions (
  version, status, effective_from, entries, created_by, activated_at
) VALUES (
  'pricing-2026-05',
  'active',
  '2026-05-01 00:00:00+00',
  '[
    {
      "provider": "anthropic",
      "model": "claude-opus-4-7",
      "rates": {
        "input_per_1k_tokens_usd": 0.015,
        "output_per_1k_tokens_usd": 0.075,
        "cached_input_per_1k_tokens_usd": 0.0015,
        "reasoning_per_1k_tokens_usd": 0.075,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "rates": {
        "input_per_1k_tokens_usd": 0.003,
        "output_per_1k_tokens_usd": 0.015,
        "cached_input_per_1k_tokens_usd": 0.0003,
        "reasoning_per_1k_tokens_usd": 0.015,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "anthropic",
      "model": "claude-haiku-4-5-20251001",
      "rates": {
        "input_per_1k_tokens_usd": 0.0008,
        "output_per_1k_tokens_usd": 0.004,
        "cached_input_per_1k_tokens_usd": 0.00008,
        "reasoning_per_1k_tokens_usd": 0.004,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "openai",
      "model": "gpt-4o",
      "rates": {
        "input_per_1k_tokens_usd": 0.0025,
        "output_per_1k_tokens_usd": 0.010,
        "cached_input_per_1k_tokens_usd": 0.00125,
        "reasoning_per_1k_tokens_usd": 0.0,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "rates": {
        "input_per_1k_tokens_usd": 0.00015,
        "output_per_1k_tokens_usd": 0.00060,
        "cached_input_per_1k_tokens_usd": 0.000075,
        "reasoning_per_1k_tokens_usd": 0.0,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "openai",
      "model": "o1",
      "rates": {
        "input_per_1k_tokens_usd": 0.015,
        "output_per_1k_tokens_usd": 0.060,
        "cached_input_per_1k_tokens_usd": 0.0075,
        "reasoning_per_1k_tokens_usd": 0.060,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "openai",
      "model": "o3-mini",
      "rates": {
        "input_per_1k_tokens_usd": 0.0011,
        "output_per_1k_tokens_usd": 0.0044,
        "cached_input_per_1k_tokens_usd": 0.00055,
        "reasoning_per_1k_tokens_usd": 0.0044,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "google",
      "model": "gemini-2.0-flash",
      "rates": {
        "input_per_1k_tokens_usd": 0.0001,
        "output_per_1k_tokens_usd": 0.0004,
        "cached_input_per_1k_tokens_usd": 0.000025,
        "reasoning_per_1k_tokens_usd": 0.0,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "google",
      "model": "gemini-2.0-flash-exp",
      "rates": {
        "input_per_1k_tokens_usd": 0.0,
        "output_per_1k_tokens_usd": 0.0,
        "cached_input_per_1k_tokens_usd": 0.0,
        "reasoning_per_1k_tokens_usd": 0.0,
        "tool_call_per_invocation_usd": 0.0
      }
    },
    {
      "provider": "google",
      "model": "gemini-1.5-pro",
      "rates": {
        "input_per_1k_tokens_usd": 0.00125,
        "output_per_1k_tokens_usd": 0.005,
        "cached_input_per_1k_tokens_usd": 0.0003125,
        "reasoning_per_1k_tokens_usd": 0.0,
        "tool_call_per_invocation_usd": 0.0
      }
    }
  ]'::jsonb,
  'migration-013',
  now()
);

-- ---------------------------------------------------------------------------
-- 6. Seed: taxonomy-v1 + 8 task types
--
--    complexity_definition JSONB schema (RFC-005 §5):
--    {
--      "classifier_version": "complexity-v1",
--      "override_rules": [{ "condition": str, "result": str, "reason": str }],
--      "dimensions": {
--        "<dim>": { "simple_max": int, "medium_max": int }
--      },
--      "scoring": { "simple_max_score": int, "complex_min_score": int }
--    }
--
--    Scoring: each dimension scores 0 (≤ simple_max), 1 (> simple_max, ≤ medium_max),
--             or 2 (> medium_max). Override rules evaluated first.
--
--    Thresholds by type (RFC-005 §5 table):
--      info_retrieval:  prompt 2000/10000  context 1/5  steps 2/6  tools 1/3
--      content_gen:     prompt 1000/8000   context 1/4  steps 2/5  tools 0/2
--      code_gen:        prompt 500/5000    context 1/6  steps 2/8  tools 1/4
--      data_analysis:   prompt 500/4000    context 1/5  steps 2/6  tools 1/3
--      orchestration:   prompt 500/5000    context 1/5  steps 3/8  tools 2/6
--      classification:  prompt 200/2000    context 0/3  steps 1/3  tools 0/2
--      conversation:    prompt 100/2000    context 0/5  steps 1/3  tools 0/2
--      evaluation:      prompt 500/4000    context 1/5  steps 2/5  tools 0/2
-- ---------------------------------------------------------------------------

DO $$
DECLARE
  v_tax_id UUID;
BEGIN

  INSERT INTO cost_intelligence.task_taxonomy_versions (
    version, status, classifier_version, created_by, activated_at
  ) VALUES (
    'taxonomy-v1', 'active', 'complexity-v1', 'migration-013', now()
  ) RETURNING id INTO v_tax_id;

  -- info_retrieval
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'info_retrieval',
    'Information Retrieval',
    'The agent''s primary work is finding, fetching, and synthesizing information from external sources or provided context.',
    '{"classifier_version":"complexity-v1","override_rules":[],"dimensions":{"prompt_chars":{"simple_max":2000,"medium_max":10000},"context_ref_count":{"simple_max":1,"medium_max":5},"declared_max_steps":{"simple_max":2,"medium_max":6},"tool_count":{"simple_max":1,"medium_max":3}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['web research','document lookup','knowledge base queries','fact extraction','literature review'],
    ARRAY['tasks that primarily generate new content (use content_gen)','tasks that primarily analyze structured data (use data_analysis)']
  );

  -- content_gen
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'content_gen',
    'Content Generation',
    'The agent''s primary work is producing original text output — writing, rewriting, summarizing, or transforming content.',
    '{"classifier_version":"complexity-v1","override_rules":[],"dimensions":{"prompt_chars":{"simple_max":1000,"medium_max":8000},"context_ref_count":{"simple_max":1,"medium_max":4},"declared_max_steps":{"simple_max":2,"medium_max":5},"tool_count":{"simple_max":0,"medium_max":2}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['drafting documents','summarizing inputs','translating content','rewriting for tone or format','generating marketing copy'],
    ARRAY['primarily retrieve rather than generate (use info_retrieval)','primarily write code (use code_gen)']
  );

  -- code_gen
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'code_gen',
    'Code Generation',
    'The agent''s primary work involves writing, modifying, reviewing, or debugging code or technical artifacts.',
    '{"classifier_version":"complexity-v1","override_rules":[],"dimensions":{"prompt_chars":{"simple_max":500,"medium_max":5000},"context_ref_count":{"simple_max":1,"medium_max":6},"declared_max_steps":{"simple_max":2,"medium_max":8},"tool_count":{"simple_max":1,"medium_max":4}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['writing functions or classes','code review','bug fixing','test generation','query writing','infrastructure configuration'],
    ARRAY['generating technical documentation without code (use content_gen)']
  );

  -- data_analysis
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'data_analysis',
    'Data Analysis',
    'The agent''s primary work is processing, analyzing, or extracting meaning from structured or semi-structured data.',
    '{"classifier_version":"complexity-v1","override_rules":[],"dimensions":{"prompt_chars":{"simple_max":500,"medium_max":4000},"context_ref_count":{"simple_max":1,"medium_max":5},"declared_max_steps":{"simple_max":2,"medium_max":6},"tool_count":{"simple_max":1,"medium_max":3}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['CSV/JSON processing','statistical analysis','data extraction','report generation from structured sources'],
    ARRAY['primarily retrieves unstructured content (use info_retrieval)','primarily writes analysis code (use code_gen)']
  );

  -- orchestration (override: declared_child_runs > 0 → complex)
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'orchestration',
    'Orchestration',
    'The agent''s primary work is coordinating, planning, or sequencing work across multiple steps or sub-agents.',
    '{"classifier_version":"complexity-v1","override_rules":[{"condition":"declared_child_runs > 0","result":"complex","reason":"Any run spawning child agents is complex by definition"}],"dimensions":{"prompt_chars":{"simple_max":500,"medium_max":5000},"context_ref_count":{"simple_max":1,"medium_max":5},"declared_max_steps":{"simple_max":3,"medium_max":8},"tool_count":{"simple_max":2,"medium_max":6}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['multi-agent pipelines','workflow planning','task decomposition','step sequencing','sub-agent delegation'],
    ARRAY['single-step agents using multiple tools','agents that call child agents only as tools without directing them']
  );

  -- classification
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'classification',
    'Classification',
    'The agent''s primary work is categorizing, tagging, labeling, or routing inputs according to a defined schema.',
    '{"classifier_version":"complexity-v1","override_rules":[],"dimensions":{"prompt_chars":{"simple_max":200,"medium_max":2000},"context_ref_count":{"simple_max":0,"medium_max":3},"declared_max_steps":{"simple_max":1,"medium_max":3},"tool_count":{"simple_max":0,"medium_max":2}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['content moderation','topic tagging','intent detection','entity recognition','routing decisions','priority assignment'],
    ARRAY['free-form evaluation without a category schema (use evaluation)']
  );

  -- conversation (override: context_ref_count > 5 → complex)
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'conversation',
    'Conversation',
    'The agent''s primary work is conducting a dialog — responding to a human turn in an ongoing conversation with conversation history.',
    '{"classifier_version":"complexity-v1","override_rules":[{"condition":"context_ref_count > 5","result":"complex","reason":"Conversations with deep context are complex by definition"}],"dimensions":{"prompt_chars":{"simple_max":100,"medium_max":2000},"context_ref_count":{"simple_max":0,"medium_max":5},"declared_max_steps":{"simple_max":1,"medium_max":3},"tool_count":{"simple_max":0,"medium_max":2}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['customer support','interactive Q&A','tutoring','assistant interactions','multi-turn dialog'],
    ARRAY['single-turn Q&A with no history (consider info_retrieval)','automated pipelines with no human in the loop']
  );

  -- evaluation
  INSERT INTO cost_intelligence.task_types (
    taxonomy_version_id, code, label, description,
    complexity_definition, primary_use_cases, exclusions
  ) VALUES (
    v_tax_id,
    'evaluation',
    'Evaluation',
    'The agent''s primary work is assessing, grading, or scoring work produced by another agent, human, or system.',
    '{"classifier_version":"complexity-v1","override_rules":[],"dimensions":{"prompt_chars":{"simple_max":500,"medium_max":4000},"context_ref_count":{"simple_max":1,"medium_max":5},"declared_max_steps":{"simple_max":2,"medium_max":5},"tool_count":{"simple_max":0,"medium_max":2}},"scoring":{"simple_max_score":1,"complex_min_score":4}}'::jsonb,
    ARRAY['code review scoring','content quality assessment','rubric-based grading','A/B output comparison','LLM-as-judge'],
    ARRAY['classification tasks where output is a category, not a quality judgment']
  );

END $$;

-- ---------------------------------------------------------------------------
-- 7. Register in schema registry (governance record, RFC-009)
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, enum_value, lifecycle_status,
  schema_version, deprecation_reason, rfc_reference
) VALUES
  ('cost_intelligence.pricing_table_versions', NULL, NULL, 'active',
   '1.0.0', 'Phase 1 Group 1 foundation — pricing table initialized.', 'RFC-002'),
  ('cost_intelligence.task_taxonomy_versions', NULL, NULL, 'active',
   '1.0.0', 'Phase 1 Group 1 foundation — task taxonomy initialized.', 'RFC-005'),
  ('cost_intelligence.task_types', NULL, NULL, 'active',
   '1.0.0', 'Phase 1 Group 1 foundation — 8 initial task types seeded (taxonomy-v1).', 'RFC-005');

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'cost_intelligence';
-- SELECT version, status, activated_at FROM cost_intelligence.pricing_table_versions;
-- SELECT version, status, classifier_version FROM cost_intelligence.task_taxonomy_versions;
-- SELECT code, label FROM cost_intelligence.task_types ORDER BY code;  -- should return 8 rows
-- SELECT COUNT(*) FROM cost_intelligence.task_types;  -- should return 8
