-- Migration 025: Codebase Context Agent - cbc Identity Registry
--   platform.cbc_identity_registry   (durable, frozen-ID, hybrid-mutability state)
--   platform.cbc_registry_events     (append-only audit of identity transitions)
--   public.cbc_* RPCs                (mint / rename / implement / merge / resolve)
--
-- Owned and written exclusively by the Codebase Context Agent (CCA).
-- Represents CODE REALITY, not product decisions - therefore PLATFORM-LEVEL and
-- tenant-NEUTRAL (a cbc:* identity is the same fact for every company/product).
-- This is the deliberate counterpart to product_graph.graph_nodes (migration 024),
-- which IS tenant-scoped because Concepts/Decisions/Questions/Features are decisions.
--
-- The CON-* -> [cbc:*] join is application-level only (graph_nodes.maps_to_codebase[]).
-- There is NO database FK between product_graph and platform.cbc_identity_registry -
-- by design, so code renames and concept re-mappings version independently.
--
-- Identity rules (sealed BA/CCA contract):
--   - cbc_id is name-derived ONLY at first mint, then FROZEN and opaque for life.
--   - Renames update current_name + append old to aka[] + emit a rename event; the ID never changes.
--   - Absent (exists:false) entities are minted 'provisional' from the normalized requested noun
--     and become authoritative on BA consumption; later implementation flips them to 'active'.
--   - Divergent-name realization is a possible_realization candidate, never a silent auto-bind.
--   - Merge collapses toward the EARLIER (BA-consumed) ID: survivor.created_at <= throwaway.created_at.
--     The throwaway becomes status='merged' pointing at the survivor; no parallel identity survives.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 012_cost_risk_engine_phase0.sql (platform schema, apply_append_only_rls)
-- Pairs with: 024_product_graph_phase1.sql

-- ---------------------------------------------------------------------------
-- 1. cbc_identity_registry - current identity state (hybrid mutability)
--    cbc_id and first_seen_sha are frozen; current_name / aka / status / source mutate.
--    Therefore NOT append-only (see LESSONS: apply_append_only_rls is not for mutable tables).
-- ---------------------------------------------------------------------------

CREATE TABLE platform.cbc_identity_registry (
  cbc_id         TEXT        NOT NULL,
  cbc_type       TEXT        NOT NULL
                   CHECK (cbc_type IN ('entity','actor','capability')),
  current_name   TEXT        NOT NULL,
  aka            TEXT[]      NOT NULL  DEFAULT '{}',
  first_seen_sha TEXT        NOT NULL,
  source         TEXT        NOT NULL  DEFAULT 'none',  -- 'table:public.vendors' | 'model:Material' | 'none'
  status         TEXT        NOT NULL  DEFAULT 'provisional'
                   CHECK (status IN ('provisional','active','merged','deprecated')),
                   -- provisional: absent noun-mint, frozen on consumption
                   -- active:      realized in code
                   -- merged:      collapsed into merged_into
                   -- deprecated:  retired
  merged_into    TEXT,                                  -- survivor cbc_id when status='merged'
  created_at     TIMESTAMPTZ NOT NULL  DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (cbc_id),

  -- the cbc_id pattern is identical to codebase-context.schema.json / product-graph.schema.json
  CONSTRAINT ck_cbc_id_format CHECK (cbc_id ~ '^cbc:(entity|actor|capability):[a-z0-9_]+$'),
  -- type segment of the id must match the stored type
  CONSTRAINT ck_cbc_type_matches CHECK (cbc_type = split_part(cbc_id, ':', 2)),
  -- merged_into present iff merged
  CONSTRAINT ck_merged_into CHECK (
    (status = 'merged' AND merged_into IS NOT NULL) OR
    (status <> 'merged' AND merged_into IS NULL)
  ),
  CONSTRAINT ck_no_self_merge CHECK (merged_into IS NULL OR merged_into <> cbc_id)
);

ALTER TABLE platform.cbc_identity_registry
  ADD CONSTRAINT fk_cbc_merged_into FOREIGN KEY (merged_into)
  REFERENCES platform.cbc_identity_registry(cbc_id) ON DELETE RESTRICT;

COMMENT ON TABLE platform.cbc_identity_registry IS
  'Frozen-ID registry of code-side identities (cbc:*). Platform-level, tenant-neutral. '
  'CCA-owned. cbc_id/first_seen_sha frozen; name/aka/status/source mutable. '
  'Join target for product_graph.graph_nodes.maps_to_codebase[] (application-level, no FK).';

CREATE INDEX ix_cbc_registry_type   ON platform.cbc_identity_registry (cbc_type, status);
CREATE INDEX ix_cbc_registry_name   ON platform.cbc_identity_registry (lower(current_name));
CREATE INDEX ix_cbc_registry_aka    ON platform.cbc_identity_registry USING GIN (aka);
CREATE INDEX ix_cbc_registry_merged ON platform.cbc_identity_registry (merged_into) WHERE merged_into IS NOT NULL;

-- Freeze guard: cbc_id and first_seen_sha are immutable; keep updated_at fresh.
CREATE OR REPLACE FUNCTION platform.enforce_cbc_frozen_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.cbc_id <> OLD.cbc_id THEN
    RAISE EXCEPTION 'cbc_id is frozen and cannot change (% -> %).', OLD.cbc_id, NEW.cbc_id;
  END IF;
  IF NEW.first_seen_sha <> OLD.first_seen_sha THEN
    RAISE EXCEPTION 'first_seen_sha is frozen for % .', OLD.cbc_id;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_cbc_frozen_fields
  BEFORE UPDATE ON platform.cbc_identity_registry
  FOR EACH ROW EXECUTE FUNCTION platform.enforce_cbc_frozen_fields();

-- ---------------------------------------------------------------------------
-- 2. cbc_registry_events - append-only audit log of identity transitions
--    Mirrors registry_event in codebase-context.schema.json.
-- ---------------------------------------------------------------------------

CREATE TABLE platform.cbc_registry_events (
  id            UUID        NOT NULL  DEFAULT gen_random_uuid(),
  cbc_id        TEXT        NOT NULL,
  event_type    TEXT        NOT NULL
                  CHECK (event_type IN ('minted','rename','implemented','collision','possible_realization','merged')),
  previous_name TEXT,
  current_name  TEXT,
  candidate_for TEXT,                                   -- possible_realization: the absent id this might realize
  survivor_id   TEXT,                                   -- merged: the id absorbed into
  commit_sha    TEXT,
  evidence      JSONB       NOT NULL  DEFAULT '{}'::jsonb,
  note          TEXT,
  created_by    TEXT        NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

ALTER TABLE platform.cbc_registry_events
  ADD CONSTRAINT fk_cbc_event_id FOREIGN KEY (cbc_id)
  REFERENCES platform.cbc_identity_registry(cbc_id) ON DELETE RESTRICT;

COMMENT ON TABLE platform.cbc_registry_events IS
  'Append-only audit of cbc identity transitions (minted/rename/implemented/collision/'
  'possible_realization/merged). Never updated. CCA-owned.';

CREATE INDEX ix_cbc_events_cbc  ON platform.cbc_registry_events (cbc_id, created_at);
CREATE INDEX ix_cbc_events_type ON platform.cbc_registry_events (event_type);

-- ---------------------------------------------------------------------------
-- 3. RLS
--    Registry: hybrid - block DELETE; allow SELECT/INSERT/UPDATE. No tenant isolation
--              (platform-level, code reality is product-neutral).
--    Events:   append-only via the canonical helper (no tenant_id -> no SELECT policy;
--              service-role / SECURITY DEFINER read only).
-- ---------------------------------------------------------------------------

ALTER TABLE platform.cbc_identity_registry ENABLE ROW LEVEL SECURITY;

CREATE POLICY "no_delete" ON platform.cbc_identity_registry
  AS RESTRICTIVE FOR DELETE USING (false);
CREATE POLICY "read_all"   ON platform.cbc_identity_registry FOR SELECT USING (true);
CREATE POLICY "insert_all" ON platform.cbc_identity_registry FOR INSERT WITH CHECK (true);
CREATE POLICY "update_all" ON platform.cbc_identity_registry FOR UPDATE USING (true);

SELECT platform.apply_append_only_rls('platform', 'cbc_registry_events');

-- ---------------------------------------------------------------------------
-- 4. RPCs (public, SECURITY DEFINER - PostgREST does not expose the platform schema)
-- ---------------------------------------------------------------------------

-- Mint a new identity or return the existing one (idempotent on cbc_id).
-- Used for both code-present ('active') and absent ('provisional') entities.
CREATE OR REPLACE FUNCTION public.cbc_register_or_get(
  p_cbc_id     TEXT,
  p_cbc_type   TEXT,
  p_name       TEXT,
  p_sha        TEXT,
  p_created_by TEXT,
  p_source     TEXT DEFAULT 'none',
  p_status     TEXT DEFAULT 'provisional'
)
RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
DECLARE v_existing TEXT;
BEGIN
  SELECT cbc_id INTO v_existing FROM platform.cbc_identity_registry WHERE cbc_id = p_cbc_id;
  IF v_existing IS NOT NULL THEN
    RETURN v_existing;
  END IF;

  INSERT INTO platform.cbc_identity_registry (
    cbc_id, cbc_type, current_name, first_seen_sha, source, status
  ) VALUES (
    p_cbc_id, p_cbc_type, p_name, p_sha, p_source, p_status
  );

  INSERT INTO platform.cbc_registry_events (cbc_id, event_type, current_name, commit_sha, created_by)
  VALUES (p_cbc_id, 'minted', p_name, p_sha, p_created_by);

  RETURN p_cbc_id;
END;
$$;

-- Rename: ID frozen; append old name to aka[]; log rename event.
CREATE OR REPLACE FUNCTION public.cbc_rename(
  p_cbc_id     TEXT,
  p_new_name   TEXT,
  p_sha        TEXT,
  p_created_by TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
DECLARE v_old TEXT;
BEGIN
  SELECT current_name INTO v_old FROM platform.cbc_identity_registry WHERE cbc_id = p_cbc_id;
  IF v_old IS NULL THEN
    RAISE EXCEPTION 'cbc_id % not found.', p_cbc_id;
  END IF;
  IF v_old = p_new_name THEN
    RETURN;
  END IF;

  UPDATE platform.cbc_identity_registry
     SET current_name = p_new_name,
         aka = (SELECT ARRAY(SELECT DISTINCT unnest(aka || ARRAY[v_old])))
   WHERE cbc_id = p_cbc_id;

  INSERT INTO platform.cbc_registry_events
    (cbc_id, event_type, previous_name, current_name, commit_sha, created_by)
  VALUES (p_cbc_id, 'rename', v_old, p_new_name, p_sha, p_created_by);
END;
$$;

-- Implement: a confident-match realization of a provisional (absent) id. provisional -> active.
CREATE OR REPLACE FUNCTION public.cbc_implement(
  p_cbc_id     TEXT,
  p_source     TEXT,
  p_sha        TEXT,
  p_created_by TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
BEGIN
  UPDATE platform.cbc_identity_registry
     SET status = 'active', source = p_source
   WHERE cbc_id = p_cbc_id AND status = 'provisional';

  IF NOT FOUND THEN
    RAISE EXCEPTION 'cbc_id % is not a provisional identity (cannot implement).', p_cbc_id;
  END IF;

  INSERT INTO platform.cbc_registry_events (cbc_id, event_type, commit_sha, note, created_by)
  VALUES (p_cbc_id, 'implemented', p_sha, 'provisional -> active: ' || p_source, p_created_by);
END;
$$;

-- Record a divergent-name realization CANDIDATE (no silent auto-bind).
-- A newly-minted active id may be the realization of a still-absent id; await human/BA confirm.
CREATE OR REPLACE FUNCTION public.cbc_propose_realization(
  p_new_cbc_id    TEXT,
  p_candidate_for TEXT,        -- the still-absent (provisional) id this might realize
  p_sha           TEXT,
  p_created_by    TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
BEGIN
  INSERT INTO platform.cbc_registry_events
    (cbc_id, event_type, candidate_for, commit_sha, note, created_by)
  VALUES (p_new_cbc_id, 'possible_realization', p_candidate_for, p_sha,
          'awaiting BA/human merge confirmation', p_created_by);
END;
$$;

-- Merge: collapse toward the EARLIER (BA-consumed) id. Enforces survivor.created_at <= throwaway.created_at.
-- Survivor absorbs throwaway's name + aka; throwaway becomes status='merged' -> survivor.
CREATE OR REPLACE FUNCTION public.cbc_merge(
  p_survivor_id  TEXT,
  p_throwaway_id TEXT,
  p_created_by   TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = platform, public
AS $$
DECLARE
  v_surv_created  TIMESTAMPTZ;
  v_throw_created TIMESTAMPTZ;
  v_throw_name    TEXT;
  v_throw_aka     TEXT[];
BEGIN
  IF p_survivor_id = p_throwaway_id THEN
    RAISE EXCEPTION 'cannot merge an id into itself (%).', p_survivor_id;
  END IF;

  SELECT created_at INTO v_surv_created  FROM platform.cbc_identity_registry WHERE cbc_id = p_survivor_id;
  SELECT created_at, current_name, aka INTO v_throw_created, v_throw_name, v_throw_aka
    FROM platform.cbc_identity_registry WHERE cbc_id = p_throwaway_id;

  IF v_surv_created IS NULL OR v_throw_created IS NULL THEN
    RAISE EXCEPTION 'both ids must exist to merge (% , %).', p_survivor_id, p_throwaway_id;
  END IF;

  -- Merge-direction rule: survivor must be the earlier-created (BA-consumed) id.
  IF v_surv_created > v_throw_created THEN
    RAISE EXCEPTION
      'merge-direction violation: survivor % is newer than throwaway %. Collapse toward the earlier id.',
      p_survivor_id, p_throwaway_id;
  END IF;

  -- Survivor absorbs the throwaway names as aliases
  UPDATE platform.cbc_identity_registry
     SET aka = (SELECT ARRAY(SELECT DISTINCT unnest(aka || ARRAY[v_throw_name] || v_throw_aka)))
   WHERE cbc_id = p_survivor_id;

  -- Throwaway is marked merged, pointing at the survivor
  UPDATE platform.cbc_identity_registry
     SET status = 'merged', merged_into = p_survivor_id
   WHERE cbc_id = p_throwaway_id;

  INSERT INTO platform.cbc_registry_events
    (cbc_id, event_type, survivor_id, note, created_by)
  VALUES (p_throwaway_id, 'merged', p_survivor_id,
          'collapsed toward earlier BA-consumed id', p_created_by);
END;
$$;

-- Resolve a code-side noun to live identities (skips merged/deprecated; follows nothing -
-- callers should treat merged rows via merged_into). Matches current_name or aka.
CREATE OR REPLACE FUNCTION public.cbc_resolve(
  p_noun TEXT
)
RETURNS TABLE (cbc_id TEXT, cbc_type TEXT, current_name TEXT, status TEXT, merged_into TEXT)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = platform, public
AS $$
  SELECT cbc_id, cbc_type, current_name, status, merged_into
  FROM platform.cbc_identity_registry
  WHERE lower(current_name) = lower(p_noun)
     OR lower(p_noun) = ANY (SELECT lower(a) FROM unnest(aka) a);
$$;

-- ---------------------------------------------------------------------------
-- 5. Governance registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version, deprecation_reason, rfc_reference
) VALUES
  ('platform.cbc_identity_registry', NULL, 'active', '1.0.0',
   'CCA v1. Frozen-ID code identity registry. Platform-level, tenant-neutral.', 'RFC-BA-001'),
  ('platform.cbc_registry_events', NULL, 'active', '1.0.0',
   'CCA v1. Append-only audit of cbc identity transitions.', 'RFC-BA-001');

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT tablename FROM pg_tables WHERE schemaname = 'platform' AND tablename LIKE 'cbc_%';
-- SELECT proname FROM pg_proc WHERE proname LIKE 'cbc_%';
-- SELECT public.cbc_register_or_get('cbc:entity:material','entity','Material','abc1234','migration-025','none','provisional');
-- SELECT cbc_id, status, current_name FROM platform.cbc_identity_registry;
