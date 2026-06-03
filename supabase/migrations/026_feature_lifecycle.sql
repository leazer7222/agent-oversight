-- Migration 026: Agent Agile Force - Lifecycle Spine
--   platform.feature_lifecycle   (one row per Feature; the FSM instance; hybrid mutability)
--   platform.lifecycle_events    (append-only audit of every state transition)
--   platform.gate_decisions      (append-only record of human review-gate outcomes)
--   public.lifecycle_* RPCs      (create / transition / record_gate / get)
--
-- Owned and written exclusively by the agile-team-orchestrator
-- (b2c3d4e5-f6a7-8901-bcde-f12345678901). The orchestrator coordinates the full
-- product-delivery lifecycle (idea -> production); see docs/agent-agile-force-lifecycle.md.
--
-- Design intent (no-redesign): the FULL set of 19 lifecycle states and all 4 human gates
-- are enumerated NOW, even though Phase 2 only drives
--   intake -> clarifying -> context_scanning -> scoping -> scope_review  (+ Gate A).
-- Phases 2.5-7 (Persona Validation / Sprint Planning / UX Design / Engineering /
-- Code Review / Release) reach states that already exist here, so later phases attach to
-- this spine without any schema change.
--
-- Amendment 2026-06-02: added two future states to the current_state CHECK -
--   'persona_validating' (Phase 2.5, optional) and 'sprint_planning' (Phase 3) - required
--   because the CHECK is a closed enumeration. Zero-cost: 026 is not yet applied. No other
--   change (no new tables/gates/decision values; the two stage outputs are ordinary
--   artifact_pointers keys). See docs/agent-agile-force-lifecycle.md Section 15a.
--
-- Storage split (sealed):
--   - The spine stores STATE + REFERENCES only. Artifact bodies stay immutable in
--     agent_outputs; feature_lifecycle.artifact_pointers holds { output_type: agent_output_id }.
--   - feature_lifecycle is hybrid: current_state / artifact_pointers / updated_at mutate;
--     feature_id / tenant_id / created_at are frozen (trigger-enforced).
--   - lifecycle_events and gate_decisions are append-only (apply_append_only_rls).
--
-- Tenant rule: tenant_id is always an explicit UUID resolved by name upstream - never LIMIT 1.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 012_cost_risk_engine_phase0.sql (platform schema, apply_append_only_rls, schema_registry)
-- Pairs with: 024_product_graph_phase1.sql, 025_cbc_identity_registry.sql

-- ---------------------------------------------------------------------------
-- 1. feature_lifecycle - the FSM instance (hybrid mutability)
-- ---------------------------------------------------------------------------

CREATE TABLE platform.feature_lifecycle (
  feature_id        UUID        NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id         UUID        NOT NULL,
  product_key       TEXT        NOT NULL,
  title             TEXT        NOT NULL,
  raw_goal          TEXT,
  current_state     TEXT        NOT NULL  DEFAULT 'intake'
                      CHECK (current_state IN (
                        -- full state set (Phases 2-7) - enumerated now, no later DDL
                        'intake',
                        'clarifying', 'clarification_blocked',
                        'persona_validating',           -- Phase 2.5 (future, optional)
                        'context_scanning',
                        'scoping', 'scoping_blocked',
                        'scope_review',
                        'sprint_planning',               -- Phase 3 (future)
                        'designing',
                        'design_review',
                        'implementing',
                        'implementation_review',
                        'code_review',
                        'final_approval',
                        'deploying',
                        'released',
                        'changes_requested',
                        'abandoned'
                      )),
  artifact_pointers JSONB       NOT NULL  DEFAULT '{}'::jsonb,  -- { <output_type>: <agent_output_id> }
  created_at        TIMESTAMPTZ NOT NULL  DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (feature_id)
);

ALTER TABLE platform.feature_lifecycle
  ADD CONSTRAINT fk_feature_tenant FOREIGN KEY (tenant_id)
  REFERENCES public.companies(id) ON DELETE RESTRICT;

COMMENT ON TABLE platform.feature_lifecycle IS
  'One row per Feature: the lifecycle FSM instance for the agile orchestrator. '
  'Stores STATE + artifact references only (never artifact bodies). Hybrid mutability: '
  'state/pointers/updated_at mutate; feature_id/tenant_id/created_at frozen.';

CREATE INDEX ix_feature_lifecycle_state  ON platform.feature_lifecycle (current_state);
CREATE INDEX ix_feature_lifecycle_tenant ON platform.feature_lifecycle (tenant_id, current_state);
CREATE INDEX ix_feature_lifecycle_prod   ON platform.feature_lifecycle (product_key);

-- Freeze guard: feature_id / tenant_id / created_at immutable; keep updated_at fresh.
CREATE OR REPLACE FUNCTION platform.enforce_feature_lifecycle_frozen()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.feature_id <> OLD.feature_id THEN
    RAISE EXCEPTION 'feature_id is frozen and cannot change (% -> %).', OLD.feature_id, NEW.feature_id;
  END IF;
  IF NEW.tenant_id <> OLD.tenant_id THEN
    RAISE EXCEPTION 'tenant_id is frozen for feature %.', OLD.feature_id;
  END IF;
  NEW.created_at := OLD.created_at;
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_feature_lifecycle_frozen
  BEFORE UPDATE ON platform.feature_lifecycle
  FOR EACH ROW EXECUTE FUNCTION platform.enforce_feature_lifecycle_frozen();

-- ---------------------------------------------------------------------------
-- 2. lifecycle_events - append-only audit of every transition
-- ---------------------------------------------------------------------------

CREATE TABLE platform.lifecycle_events (
  id           UUID        NOT NULL  DEFAULT gen_random_uuid(),
  feature_id   UUID        NOT NULL,
  from_state   TEXT,                                   -- null on the initial 'create' event
  to_state     TEXT        NOT NULL,
  actor        TEXT        NOT NULL,                   -- 'agent:<uuid>' | 'human:<email>' | 'system'
  decision     TEXT        NOT NULL
                 CHECK (decision IN (
                   'create','advance','approve','request_changes','blocked','answers','abandon'
                 )),
  target_state TEXT,                                   -- loopback target on request_changes
  run_id       UUID,                                   -- the agent run that drove the transition (nullable)
  note         TEXT,
  created_at   TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

ALTER TABLE platform.lifecycle_events
  ADD CONSTRAINT fk_lifecycle_event_feature FOREIGN KEY (feature_id)
  REFERENCES platform.feature_lifecycle(feature_id) ON DELETE RESTRICT;

COMMENT ON TABLE platform.lifecycle_events IS
  'Append-only audit of feature lifecycle transitions. Never updated. Orchestrator-owned.';

CREATE INDEX ix_lifecycle_events_feature ON platform.lifecycle_events (feature_id, created_at);
CREATE INDEX ix_lifecycle_events_to      ON platform.lifecycle_events (to_state);

-- ---------------------------------------------------------------------------
-- 3. gate_decisions - append-only record of human review-gate outcomes
-- ---------------------------------------------------------------------------

CREATE TABLE platform.gate_decisions (
  id              UUID        NOT NULL  DEFAULT gen_random_uuid(),
  feature_id      UUID        NOT NULL,
  gate            TEXT        NOT NULL  CHECK (gate IN ('A','B','C','D')),
  decision        TEXT        NOT NULL  CHECK (decision IN ('approve','request_changes','hold')),
  reviewer        TEXT        NOT NULL,                -- 'human:<email>'
  change_requests JSONB       NOT NULL  DEFAULT '[]'::jsonb,
  note            TEXT,
  created_at      TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

ALTER TABLE platform.gate_decisions
  ADD CONSTRAINT fk_gate_decision_feature FOREIGN KEY (feature_id)
  REFERENCES platform.feature_lifecycle(feature_id) ON DELETE RESTRICT;

COMMENT ON TABLE platform.gate_decisions IS
  'Append-only record of human review-gate outcomes (A=Product, B=Design, C=Engineering, '
  'D=Final). All four gates enumerated now; Phase 2 exercises only Gate A.';

CREATE INDEX ix_gate_decisions_feature ON platform.gate_decisions (feature_id, gate);

-- ---------------------------------------------------------------------------
-- 4. RLS
--    feature_lifecycle: hybrid - block DELETE; allow SELECT/INSERT/UPDATE.
--      Tenant-isolation policy deferred (Phase 2 uses service-role + explicit tenant_id);
--      it is additive later and needs no schema change.
--    events / gate_decisions: append-only via the canonical helper (read via SECURITY
--      DEFINER RPCs).
-- ---------------------------------------------------------------------------

ALTER TABLE platform.feature_lifecycle ENABLE ROW LEVEL SECURITY;

CREATE POLICY "no_delete" ON platform.feature_lifecycle
  AS RESTRICTIVE FOR DELETE USING (false);
CREATE POLICY "read_all"   ON platform.feature_lifecycle FOR SELECT USING (true);
CREATE POLICY "insert_all" ON platform.feature_lifecycle FOR INSERT WITH CHECK (true);
CREATE POLICY "update_all" ON platform.feature_lifecycle FOR UPDATE USING (true);

SELECT platform.apply_append_only_rls('platform', 'lifecycle_events');
SELECT platform.apply_append_only_rls('platform', 'gate_decisions');

-- ---------------------------------------------------------------------------
-- 5. RPCs (public, SECURITY DEFINER - PostgREST does not expose the platform schema)
-- ---------------------------------------------------------------------------

-- Create a Feature at 'intake' and log the create event. tenant_id resolved upstream (never LIMIT 1).
CREATE OR REPLACE FUNCTION public.lifecycle_create_feature(
  p_tenant_id   UUID,
  p_product_key TEXT,
  p_title       TEXT,
  p_raw_goal    TEXT,
  p_created_by  TEXT
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
DECLARE v_feature_id UUID;
BEGIN
  INSERT INTO platform.feature_lifecycle (tenant_id, product_key, title, raw_goal, current_state)
  VALUES (p_tenant_id, p_product_key, p_title, p_raw_goal, 'intake')
  RETURNING feature_id INTO v_feature_id;

  INSERT INTO platform.lifecycle_events (feature_id, from_state, to_state, actor, decision, note)
  VALUES (v_feature_id, NULL, 'intake', p_created_by, 'create', 'feature created');

  RETURN v_feature_id;
END;
$$;

-- Atomic transition: update state, merge an artifact pointer (optional), append an event.
-- Used for agent advances and for loopbacks (pass p_decision='request_changes' + p_target_state).
CREATE OR REPLACE FUNCTION public.lifecycle_transition(
  p_feature_id    UUID,
  p_to_state      TEXT,
  p_actor         TEXT,
  p_decision      TEXT,
  p_run_id        UUID DEFAULT NULL,
  p_artifact_type TEXT DEFAULT NULL,
  p_artifact_id   UUID DEFAULT NULL,
  p_target_state  TEXT DEFAULT NULL,
  p_note          TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
DECLARE v_from TEXT;
BEGIN
  SELECT current_state INTO v_from FROM platform.feature_lifecycle WHERE feature_id = p_feature_id;
  IF v_from IS NULL THEN
    RAISE EXCEPTION 'feature_id % not found.', p_feature_id;
  END IF;

  UPDATE platform.feature_lifecycle
     SET current_state = p_to_state,
         artifact_pointers = CASE
           WHEN p_artifact_type IS NOT NULL AND p_artifact_id IS NOT NULL
           THEN artifact_pointers || jsonb_build_object(p_artifact_type, p_artifact_id::text)
           ELSE artifact_pointers
         END
   WHERE feature_id = p_feature_id;

  INSERT INTO platform.lifecycle_events
    (feature_id, from_state, to_state, actor, decision, target_state, run_id, note)
  VALUES (p_feature_id, v_from, p_to_state, p_actor, p_decision, p_target_state, p_run_id, p_note);
END;
$$;

-- Record a human gate decision, transition state, append an event - atomically.
CREATE OR REPLACE FUNCTION public.lifecycle_record_gate(
  p_feature_id      UUID,
  p_gate            TEXT,
  p_decision        TEXT,
  p_reviewer        TEXT,
  p_to_state        TEXT,
  p_change_requests JSONB DEFAULT '[]'::jsonb,
  p_target_state    TEXT DEFAULT NULL,
  p_note            TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
DECLARE v_from TEXT;
BEGIN
  SELECT current_state INTO v_from FROM platform.feature_lifecycle WHERE feature_id = p_feature_id;
  IF v_from IS NULL THEN
    RAISE EXCEPTION 'feature_id % not found.', p_feature_id;
  END IF;

  INSERT INTO platform.gate_decisions (feature_id, gate, decision, reviewer, change_requests, note)
  VALUES (p_feature_id, p_gate, p_decision, p_reviewer, p_change_requests, p_note);

  UPDATE platform.feature_lifecycle SET current_state = p_to_state WHERE feature_id = p_feature_id;

  INSERT INTO platform.lifecycle_events
    (feature_id, from_state, to_state, actor, decision, target_state, note)
  VALUES (p_feature_id, v_from, p_to_state, p_reviewer,
          CASE WHEN p_decision = 'approve' THEN 'approve' ELSE 'request_changes' END,
          p_target_state, COALESCE(p_note, 'gate ' || p_gate || ': ' || p_decision));
END;
$$;

-- Read a feature row (incl. artifact pointers) as jsonb.
CREATE OR REPLACE FUNCTION public.lifecycle_get(
  p_feature_id UUID
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = platform, public
AS $$
  SELECT to_jsonb(fl) FROM platform.feature_lifecycle fl WHERE fl.feature_id = p_feature_id;
$$;

-- ---------------------------------------------------------------------------
-- 6. Governance registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version, deprecation_reason, rfc_reference
) VALUES
  ('platform.feature_lifecycle', NULL, 'active', '1.0.0',
   'Agent Agile Force v1. Lifecycle FSM instance. State + references only.', 'RFC-AAF-001'),
  ('platform.lifecycle_events', NULL, 'active', '1.0.0',
   'Agent Agile Force v1. Append-only audit of lifecycle transitions.', 'RFC-AAF-001'),
  ('platform.gate_decisions', NULL, 'active', '1.0.0',
   'Agent Agile Force v1. Append-only human review-gate outcomes.', 'RFC-AAF-001');

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT tablename FROM pg_tables WHERE schemaname = 'platform'
--   AND tablename IN ('feature_lifecycle','lifecycle_events','gate_decisions');
-- SELECT proname FROM pg_proc WHERE proname LIKE 'lifecycle_%';
-- SELECT public.lifecycle_create_feature(
--   (SELECT id FROM public.companies WHERE name = 'ReformAI'),
--   'reformai-product', 'Materials catalogue', 'Add a catalogue of materials', 'migration-026');
-- SELECT public.lifecycle_get(feature_id) FROM platform.feature_lifecycle LIMIT 1;
