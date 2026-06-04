-- Migration 043: Gate A snapshot table (P2, step 4, Option B)
--
-- A human Gate A approval is not an agent run, so it does not belong in agent_outputs (whose run_id
-- is NOT NULL and FKs to runs, which itself requires task_type_id/classifier). Instead, the immutable
-- Gate A snapshot lives in its own append-only table. Public schema so the dashboard can read/write it
-- via PostgREST (like agent_outputs). Immutability via apply_append_only_rls (block UPDATE/DELETE;
-- tenant-isolated SELECT). Writes go through the service role (bypasses RLS).
--
-- Supersession: a re-approval inserts a NEW row with supersedes = prior id; never an edit.
-- Plan: docs/p2-rule-attribute-gate-a-plan.md (section 11). Depends on: 012 (apply_append_only_rls).

CREATE TABLE public.gate_a_snapshots (
  id                uuid        NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id         uuid        NOT NULL,
  product_key       text        NOT NULL,
  feature_key       text        NOT NULL,
  content_hash      text        NOT NULL,
  manifest          jsonb       NOT NULL,   -- { node_keys[], node_uuids[], edges[] }
  rendered_markdown text        NOT NULL,   -- the human Feature Spec
  provenance        jsonb       NOT NULL,   -- { codebase_context_artifact_id, commit_sha, accepted_decisions[], ... }
  pm_layer          jsonb       NOT NULL  DEFAULT '{}'::jsonb,
  approved_by       text        NOT NULL,
  supersedes        uuid,                   -- prior snapshot for this feature
  created_at        timestamptz NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

ALTER TABLE public.gate_a_snapshots
  ADD CONSTRAINT fk_gate_a_supersedes FOREIGN KEY (supersedes)
  REFERENCES public.gate_a_snapshots(id) ON DELETE RESTRICT;

CREATE INDEX ix_gate_a_snapshots_feature ON public.gate_a_snapshots (product_key, feature_key, created_at DESC);

COMMENT ON TABLE public.gate_a_snapshots IS
  'Immutable Gate A Feature Spec snapshots. Append-only; re-approval supersedes. The graph is the '
  'source of truth; this is a pinned, auditable baseline (manifest of node UUIDs + content hash).';

SELECT platform.apply_append_only_rls('public', 'gate_a_snapshots');
