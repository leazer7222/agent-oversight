-- Migration 011: code-review-agent — capability definition + ReformAI instance
-- Apply to live project: hdhovyrlnfojtkqbcegh
--
-- What this does:
--   1. Expands agent_outputs.output_type CHECK to include 'code_review'
--   2. Registers code-review-agent as a reusable capability definition
--   3. Registers reformai.code-review-agent as the ReformAI operational instance
--
-- Naming convention introduced here:
--   Definitions : {capability}           e.g. code-review-agent
--   Instances   : {tenant}.{capability}  e.g. reformai.code-review-agent
--
-- The hierarchy page displays instances only. Definitions are a library catalog.
-- See docs/PLATFORM_ARCHITECTURE.md for the definition/instance architecture.

-- ---------------------------------------------------------------------------
-- 1. Expand agent_outputs.output_type CHECK to include 'code_review'
--    Preserves all existing types: marketing_brief, lp_blueprint,
--    strategy_summary, context_snapshot, ui_components, other.
-- ---------------------------------------------------------------------------

ALTER TABLE agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;

ALTER TABLE agent_outputs ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type = ANY (ARRAY[
    'marketing_brief'::text,
    'lp_blueprint'::text,
    'strategy_summary'::text,
    'context_snapshot'::text,
    'ui_components'::text,
    'code_review'::text,
    'other'::text
  ]));

-- ---------------------------------------------------------------------------
-- 2. code-review-agent: reusable capability definition
--
--    Tenant-neutral. Defines:
--      - input_schema  : what the agent receives (diff, commit_sha, etc.)
--      - output_schema : the immutable code_review findings artifact contract
--      - config_schema : what operational instances may override
--
--    All instances of this definition produce the same output shape.
--    Jurisdiction, standards refs, and context scope are instance concerns
--    (set via config_overrides on the agents row).
--
--    Semantic distinction from engineering-review-agent:
--      engineering-review-agent — strategic/design review; general quality
--      code-review-agent        — structured pre-push safety; produces an
--                                 immutable findings artifact with severity
--                                 taxonomy, confidence levels, and principle
--                                 references; output_type = 'code_review'
-- ---------------------------------------------------------------------------

INSERT INTO agent_definitions (
  id,
  name,
  display_name,
  description,
  capability_tags,
  instance_type,
  default_model,
  input_schema,
  output_schema,
  config_schema,
  version,
  source_path
) VALUES (
  'f9a8b7c6-d5e4-4f3a-8b2c-1d0e9f8a7b6c',
  'code-review-agent',
  'Code Review Agent',
  'Performs structured pre-push code review against documented architecture principles, governance standards, and operational conventions. Produces an immutable code_review findings artifact with severity taxonomy, confidence levels, principle references, and remediation guidance. Advisory in v1 — recommendations are not automated gates.',
  ARRAY['code_review', 'quality_assurance', 'architecture_review', 'governance_review'],
  'stateless',
  NULL,
  '{
    "type": "object",
    "required": ["diff", "commit_sha"],
    "properties": {
      "diff": {
        "type": "string",
        "description": "Unified diff of the changes to review"
      },
      "changed_files": {
        "type": "array",
        "items": {"type": "string"},
        "description": "File paths that were changed"
      },
      "commit_sha": {
        "type": "string",
        "description": "Commit SHA being reviewed — immutable provenance reference"
      },
      "base_sha": {
        "type": "string",
        "description": "Base commit SHA the diff is computed from"
      },
      "branch": {
        "type": "string",
        "description": "Branch being reviewed"
      },
      "pr_number": {
        "type": ["integer", "null"],
        "description": "Pull request number if available; null for pre-push reviews"
      },
      "standards_refs": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Paths to standards documents to apply during this review"
      },
      "review_mode": {
        "type": "string",
        "enum": ["pre-push", "pr", "commit", "branch"],
        "default": "pre-push"
      }
    }
  }',
  '{
    "type": "object",
    "required": [
      "schema_version", "review_id", "subject", "context_applied",
      "findings", "severity_counts", "category_counts", "recommendation", "summary"
    ],
    "properties": {
      "schema_version": {
        "type": "string",
        "description": "Output schema version for forward-compatibility"
      },
      "review_id": {
        "type": "string",
        "format": "uuid",
        "description": "Stable UUID for this review artifact"
      },
      "subject": {
        "type": "object",
        "required": ["type", "commit_sha"],
        "properties": {
          "type": {"type": "string", "enum": ["diff", "commit", "branch", "pr"]},
          "commit_sha": {"type": "string"},
          "base_sha": {"type": "string"},
          "branch": {"type": "string"},
          "pr_number": {"type": ["integer", "null"]},
          "files_examined": {"type": "array", "items": {"type": "string"}},
          "lines_examined": {"type": "integer"}
        }
      },
      "context_applied": {
        "type": "object",
        "properties": {
          "definition_version": {"type": "string"},
          "agent_instance": {"type": "string"},
          "standards_refs": {"type": "array", "items": {"type": "string"}},
          "review_mode": {"type": "string"},
          "tenant": {"type": "string"},
          "project": {"type": "string"}
        }
      },
      "findings": {
        "type": "array",
        "items": {
          "type": "object",
          "required": [
            "finding_id", "sequence", "category", "severity",
            "confidence", "blocking", "title", "explanation", "remediation"
          ],
          "properties": {
            "finding_id": {
              "type": "string",
              "format": "uuid",
              "description": "Stable identifier — enables future lifecycle state tracking"
            },
            "sequence": {
              "type": "integer",
              "description": "Ordering within this review artifact"
            },
            "category": {
              "type": "string",
              "enum": [
                "architecture", "observability", "governance", "schema",
                "security", "type_safety", "operational_semantics",
                "naming", "documentation"
              ]
            },
            "severity": {
              "type": "string",
              "enum": ["critical", "warning", "info"],
              "description": "critical=operational risk; warning=pattern drift; info=observational"
            },
            "confidence": {
              "type": "string",
              "enum": ["high", "medium", "low"],
              "description": "high=explicit pattern match; medium=likely; low=possible false positive"
            },
            "blocking": {
              "type": "boolean",
              "description": "Whether the agent recommends gating this finding. Advisory only in v1."
            },
            "title": {"type": "string"},
            "explanation": {
              "type": "string",
              "description": "Why this is a finding — backward-looking, describes what was observed"
            },
            "remediation": {
              "type": "string",
              "description": "What the author should do — forward-looking and actionable"
            },
            "affected_files": {
              "type": "array",
              "items": {"type": "string"}
            },
            "line_references": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "file": {"type": "string"},
                  "start_line": {"type": "integer"},
                  "end_line": {"type": "integer"}
                }
              }
            },
            "principles": {
              "type": "array",
              "items": {"type": "string"},
              "description": "PLATFORM_ARCHITECTURE.md principle IDs e.g. [\"P5\", \"P6\"]"
            },
            "standards_refs": {
              "type": "array",
              "items": {"type": "string"},
              "description": "Anchors finding to a specific documented standard — makes it contestable"
            },
            "lessons_refs": {
              "type": "array",
              "items": {"type": "string"},
              "description": "References to LESSONS_LEARNED.md entries if applicable"
            },
            "operational_risk": {
              "type": "string",
              "description": "What could go wrong operationally if this finding is ignored"
            },
            "governance_implication": {
              "type": "string",
              "description": "Any impact on the control plane, observability, or ledger integrity"
            }
          }
        }
      },
      "severity_counts": {
        "type": "object",
        "properties": {
          "critical": {"type": "integer"},
          "warning": {"type": "integer"},
          "info": {"type": "integer"}
        }
      },
      "category_counts": {
        "type": "object",
        "description": "Per-category finding counts — keys match category enum"
      },
      "recommendation": {
        "type": "string",
        "enum": ["approve", "approve_with_warnings", "review_required", "block"],
        "description": "Advisory recommendation only. approve=safe; approve_with_warnings=minor issues; review_required=human judgment needed; block=clear violation or safety risk"
      },
      "governance_flags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Short labels for governance-relevant signals e.g. [\"missing_telemetry\", \"schema_drift\"]"
      },
      "summary": {
        "type": "string",
        "description": "One-paragraph human-readable summary of the review"
      }
    }
  }',
  '{
    "type": "object",
    "properties": {
      "context_scope": {
        "type": "object",
        "properties": {
          "standards_refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Standards documents to apply during review"
          },
          "architecture_docs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Architecture reference documents"
          }
        }
      },
      "review_mode": {
        "type": "string",
        "enum": ["pre-push", "pr", "commit", "branch"],
        "default": "pre-push"
      },
      "tenant": {"type": "string"},
      "project": {"type": "string"},
      "review_scope": {
        "type": "string",
        "description": "Human-readable description of what is in scope"
      },
      "exclusions": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Tenant slugs excluded from this instance scope"
      }
    }
  }',
  '1.0.0',
  'agents/library/code-review-agent/agent.py'
)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. reformai.code-review-agent: operational instance
--
--    Tenant   : ReformAI (1021c018-fe0e-4ae8-a972-7487521cc3d9)
--    Project  : Agent Oversight (project_id null — projects table currently empty)
--    Parent   : claude-reformai (f239fe0a-2134-489d-b13a-6bcf2aaf1ef5)
--    Type     : worker | Depth: 1
--    Trigger  : manual (invoked by claude-reformai only)
--
--    Authorization: only claude-reformai may trigger this instance.
--    Personal and AfterGlow orchestrators are excluded via can_be_triggered_by.
--
--    v1 is advisory only. Findings are written to agent_outputs with
--    output_type='code_review'. No automated gating. No lifecycle state table.
--    Future: lifecycle state table, CI integration, trust accumulation signals.
-- ---------------------------------------------------------------------------

INSERT INTO agents (
  id,
  name,
  company_id,
  project_id,
  definition_id,
  agent_type,
  parent_agent_id,
  depth,
  trigger_type,
  trigger_config,
  status,
  max_errors_per_hour,
  priority,
  tags,
  can_trigger,
  can_be_triggered_by,
  config_overrides,
  registered_at,
  metadata
) VALUES (
  'a0b9c8d7-e6f5-4a4b-9c3d-2e1f0a9b8c7d',
  'reformai.code-review-agent',
  '1021c018-fe0e-4ae8-a972-7487521cc3d9',
  NULL,
  'f9a8b7c6-d5e4-4f3a-8b2c-1d0e9f8a7b6c',
  'worker',
  'f239fe0a-2134-489d-b13a-6bcf2aaf1ef5',
  1,
  'manual',
  '{}',
  'active',
  10,
  5,
  ARRAY['code_review', 'quality_assurance', 'pre-push'],
  ARRAY[]::uuid[],
  ARRAY['f239fe0a-2134-489d-b13a-6bcf2aaf1ef5']::uuid[],
  '{
    "tenant": "reformai",
    "project": "agent-oversight",
    "review_mode": "pre-push",
    "context_scope": {
      "standards_refs": [
        "docs/PLATFORM_ARCHITECTURE.md",
        "docs/repo-standards.md",
        "docs/agent-standards.md"
      ],
      "architecture_docs": [
        "docs/PLATFORM_ARCHITECTURE.md"
      ]
    },
    "review_scope": "agent-oversight repository",
    "exclusions": ["personal", "afterglow"]
  }',
  now(),
  '{
    "v1_note": "Advisory only. Findings written to agent_outputs with output_type=code_review. Lifecycle state table deferred per graduation pattern."
  }'
)
ON CONFLICT (id) DO NOTHING;
