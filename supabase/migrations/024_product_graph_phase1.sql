-- Migration 024: Product Intelligence Graph - Phase 1 (BA Agent v1)
--   product_graph schema
--   graph_nodes   (polymorphic: feature | concept | question | decision)
--   graph_edges   (references | resolves | supersedes | derived_from)
--   Immutability trigger (accepted/terminal nodes are content-frozen; supersede, never edit)
--   Hybrid RLS on graph_nodes (INSERT + UPDATE for lifecycle transitions; no DELETE)
--   Append-only RLS on graph_edges
--   public.* SECURITY DEFINER RPCs (PostgREST does not expose non-public schemas)
--
-- Pairs with migration 025 (cbc_identity_registry, owned by the Codebase Context Agent).
-- The join is one-directional: graph_nodes(concept).maps_to_codebase[] -> cbc_identity_registry.cbc_id.
-- The registry never references CON-* nodes.
--
-- v1 graph primitives (per BA/CCA sealed contract):
--   Knowledge plane: Concept, Decision   (+ Rule, Attribute DEFERRED)
--   Process plane:   Feature, Question    (+ Assumption DEFERRED)
-- Decisions carry forward-compat stubs (implies_rules / implies_attributes in node_attributes)
-- so Rule/Attribute can be promoted later by migration, not re-litigated.
--
-- Epistemic status (fact | claim | assumption) is DERIVED from (node_type, status),
-- never stored. See public.graph_node_epistemic_status().
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 012_cost_risk_engine_phase0.sql (platform.apply_append_only_rls)

-- ---------------------------------------------------------------------------
-- 1. Schema
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS product_graph;

-- ---------------------------------------------------------------------------
-- 2. graph_nodes - polymorphic node table
--
--    node_key is the stable, human-readable, opaque-after-mint identifier
--    (FEAT-*, CON-*, QST-*, DEC-*). The BA Agent owns minting. UUID id is the
--    surrogate PK used for edges so renames of node_key never cascade.
--
--    Mutable table (status transitions, ratification). NOT append-only.
--    Content immutability after 'accepted' is enforced by trigger, not RLS.
-- ---------------------------------------------------------------------------

CREATE TABLE product_graph.graph_nodes (
  id               UUID        NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id        UUID        NOT NULL,                 -- company isolation (see LESSONS: never LIMIT 1)
  product_key      TEXT        NOT NULL,                 -- mirrors codebase-context target_key, e.g. 'reformai-product'
  node_type        TEXT        NOT NULL
                     CHECK (node_type IN ('feature','concept','question','decision')),
  node_key         TEXT        NOT NULL,                 -- FEAT-/CON-/QST-/DEC- stable id
  title            TEXT        NOT NULL,                 -- intent | name | question text | decision statement
  status           TEXT        NOT NULL,
  kind             TEXT,                                 -- concept only: actor | entity | workflow | event | ...
  blocking         BOOLEAN,                              -- question only
  divergence       TEXT                                  -- question only: low | medium | high
                     CHECK (divergence IS NULL OR divergence IN ('low','medium','high')),
  maps_to_codebase TEXT[]      NOT NULL  DEFAULT '{}',   -- concept only: cbc:* identities (drift-detection join key)
  aliases          TEXT[]      NOT NULL  DEFAULT '{}',   -- concept only: synonym folding (anti-duplicate)
  node_attributes  JSONB       NOT NULL  DEFAULT '{}'::jsonb,
                     -- decision: { rationale, implies_rules:[...], implies_attributes:[{concept,fields:[...]}] }
                     -- feature:  { scoped_against_commit, notes:[...] }
  ratified_by      TEXT,                                 -- set only on transition into accepted/handed_off
  ratified_at      TIMESTAMPTZ,
  created_by       TEXT        NOT NULL,                 -- 'ba-agent' or human operator id
  created_at       TIMESTAMPTZ NOT NULL  DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),

  -- node_key is globally unique per product
  CONSTRAINT uq_graph_node_key UNIQUE (product_key, node_key),

  -- key prefix must match node_type
  CONSTRAINT ck_node_key_prefix CHECK (
    (node_type = 'feature'  AND node_key LIKE 'FEAT-%') OR
    (node_type = 'concept'  AND node_key LIKE 'CON-%')  OR
    (node_type = 'question' AND node_key LIKE 'QST-%')  OR
    (node_type = 'decision' AND node_key LIKE 'DEC-%')
  ),

  -- per-type lifecycle state machines
  CONSTRAINT ck_node_status CHECK (
    (node_type = 'feature'  AND status IN ('scoping','ready','handed_off','shelved')) OR
    (node_type = 'concept'  AND status IN ('proposed','accepted','rejected','deprecated')) OR
    (node_type = 'question' AND status IN ('open','answered','deferred')) OR
    (node_type = 'decision' AND status IN ('proposed','accepted','rejected','superseded'))
  ),

  -- type-scoped attribute hygiene: concept-only and question-only columns
  CONSTRAINT ck_kind_concept_only       CHECK (kind IS NULL OR node_type = 'concept'),
  CONSTRAINT ck_blocking_question_only  CHECK (blocking IS NULL OR node_type = 'question'),
  CONSTRAINT ck_divergence_question_only CHECK (divergence IS NULL OR node_type = 'question'),
  CONSTRAINT ck_mapping_concept_only    CHECK (
    (maps_to_codebase = '{}' AND aliases = '{}') OR node_type = 'concept'
  )
);

COMMENT ON TABLE product_graph.graph_nodes IS
  'Polymorphic product-intelligence graph nodes (feature/concept/question/decision). '
  'node_key is the stable BA-owned identifier; id is the surrogate edge target. '
  'Mutable for lifecycle transitions; content frozen after acceptance by trigger. '
  'Epistemic status is derived, never stored.';

CREATE INDEX ix_graph_nodes_type_status ON product_graph.graph_nodes (product_key, node_type, status);
CREATE INDEX ix_graph_nodes_kind        ON product_graph.graph_nodes (product_key, kind) WHERE node_type = 'concept';
CREATE INDEX ix_graph_nodes_maps_cbc    ON product_graph.graph_nodes USING GIN (maps_to_codebase);
CREATE INDEX ix_graph_nodes_aliases     ON product_graph.graph_nodes USING GIN (aliases);

-- ---------------------------------------------------------------------------
-- 3. graph_edges - typed relationships
--    Append-only: edges are never updated. Superseding adds a new edge; the
--    old one remains as history. Edges to rejected nodes are retained (audit);
--    retrieval filters by node status.
-- ---------------------------------------------------------------------------

CREATE TABLE product_graph.graph_edges (
  id              UUID        NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id       UUID        NOT NULL,
  product_key     TEXT        NOT NULL,
  edge_type       TEXT        NOT NULL
                    CHECK (edge_type IN ('references','resolves','supersedes','derived_from')),
  src_node_id     UUID        NOT NULL,
  dst_node_id     UUID        NOT NULL,
  edge_attributes JSONB       NOT NULL  DEFAULT '{}'::jsonb,  -- references: { nature: touches|creates|modifies }
  created_by      TEXT        NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT uq_graph_edge UNIQUE (edge_type, src_node_id, dst_node_id),
  CONSTRAINT ck_edge_no_self_loop CHECK (src_node_id <> dst_node_id)
);

ALTER TABLE product_graph.graph_edges
  ADD CONSTRAINT fk_edge_src FOREIGN KEY (src_node_id)
  REFERENCES product_graph.graph_nodes(id) ON DELETE RESTRICT;

ALTER TABLE product_graph.graph_edges
  ADD CONSTRAINT fk_edge_dst FOREIGN KEY (dst_node_id)
  REFERENCES product_graph.graph_nodes(id) ON DELETE RESTRICT;

COMMENT ON TABLE product_graph.graph_edges IS
  'Typed graph edges. Append-only. supersedes/resolves/derived_from/references. '
  'references.nature lives in edge_attributes.';

CREATE INDEX ix_graph_edges_src ON product_graph.graph_edges (src_node_id, edge_type);
CREATE INDEX ix_graph_edges_dst ON product_graph.graph_edges (dst_node_id, edge_type);

-- ---------------------------------------------------------------------------
-- 4. Immutability trigger
--    Once a node reaches a terminal/ratified state, its content is frozen.
--    The ONLY permitted update from 'accepted' is the transition to
--    'superseded'/'deprecated' (status-only). Everything else must supersede.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION product_graph.enforce_node_immutability()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  -- Frozen states: ratified knowledge or closed process nodes
  IF OLD.status IN ('accepted','handed_off','rejected','superseded','deprecated') THEN
    -- Allow only a status move to a later terminal state; block content edits
    IF NEW.title           IS DISTINCT FROM OLD.title
       OR NEW.kind         IS DISTINCT FROM OLD.kind
       OR NEW.node_attributes IS DISTINCT FROM OLD.node_attributes
       OR NEW.maps_to_codebase IS DISTINCT FROM OLD.maps_to_codebase
       OR NEW.blocking     IS DISTINCT FROM OLD.blocking
       OR NEW.divergence   IS DISTINCT FROM OLD.divergence THEN
      RAISE EXCEPTION
        'Node % is in frozen state % - content is immutable. Supersede it with a new node instead.',
        OLD.node_key, OLD.status;
    END IF;

    -- Permit only accepted->superseded / accepted->deprecated status moves
    IF NEW.status <> OLD.status
       AND NOT (OLD.status = 'accepted' AND NEW.status IN ('superseded','deprecated')) THEN
      RAISE EXCEPTION
        'Illegal transition % -> % on node % (frozen).', OLD.status, NEW.status, OLD.node_key;
    END IF;
  END IF;

  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_node_immutability
  BEFORE UPDATE ON product_graph.graph_nodes
  FOR EACH ROW EXECUTE FUNCTION product_graph.enforce_node_immutability();

-- ---------------------------------------------------------------------------
-- 5. RLS
--    graph_nodes: hybrid (LESSONS - apply_append_only_rls is NOT for mutable tables).
--                 Block DELETE; allow INSERT + UPDATE; tenant isolation on SELECT.
--    graph_edges: append-only via the canonical helper.
-- ---------------------------------------------------------------------------

ALTER TABLE product_graph.graph_nodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "no_delete" ON product_graph.graph_nodes
  AS RESTRICTIVE FOR DELETE USING (false);

CREATE POLICY "tenant_isolation_select" ON product_graph.graph_nodes
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY "tenant_insert" ON product_graph.graph_nodes
  FOR INSERT
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY "tenant_update" ON product_graph.graph_nodes
  FOR UPDATE
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

SELECT platform.apply_append_only_rls('product_graph', 'graph_edges');

-- ---------------------------------------------------------------------------
-- 6. Derived epistemic status (never stored)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.graph_node_epistemic_status(
  p_node_type TEXT, p_status TEXT
)
RETURNS TEXT
LANGUAGE sql IMMUTABLE
AS $$
  SELECT CASE
    WHEN p_node_type IN ('concept','decision') AND p_status = 'accepted' THEN 'fact'
    WHEN p_node_type IN ('concept','decision') AND p_status = 'proposed' THEN 'claim'
    WHEN p_node_type = 'question'                                        THEN 'open'
    WHEN p_node_type = 'feature'                                         THEN 'process'
    ELSE 'none'
  END;
$$;

-- ---------------------------------------------------------------------------
-- 6b. Node-key minting (Decision 1)
--    The BA runtime does NOT generate node keys itself; it calls this RPC.
--    Keys are opaque, zero-padded sequential per (product_key, node_type):
--    FEAT-0001, CON-0001, QST-0001, DEC-0001. The human-readable name lives in
--    graph_nodes.title, NOT the key.
--
--    v1 ASSUMPTION: the BA Agent is the SOLE writer, so MAX(suffix)+1 is
--    race-free in practice; any duplicate from a race is caught by the
--    UNIQUE (product_key, node_key) constraint. Multi-writer support can
--    replace this body (e.g. a per-(product,type) sequence table) WITHOUT
--    changing the BA runtime or this signature.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.graph_next_key(
  p_product   TEXT,
  p_node_type TEXT
)
RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = product_graph, public
AS $$
DECLARE
  v_prefix TEXT;
  v_next   INT;
BEGIN
  v_prefix := CASE p_node_type
    WHEN 'feature'  THEN 'FEAT-'
    WHEN 'concept'  THEN 'CON-'
    WHEN 'question' THEN 'QST-'
    WHEN 'decision' THEN 'DEC-'
    ELSE NULL
  END;
  IF v_prefix IS NULL THEN
    RAISE EXCEPTION 'graph_next_key: unknown node_type %', p_node_type;
  END IF;

  -- Numbering is scoped to product_key to match UNIQUE (product_key, node_key).
  -- Only purely-numeric keys of this prefix participate; legacy semantic keys
  -- (if any) are ignored by the regex filter.
  SELECT COALESCE(MAX((substring(node_key FROM '[0-9]+$'))::int), 0) + 1
    INTO v_next
  FROM product_graph.graph_nodes
  WHERE product_key = p_product
    AND node_type   = p_node_type
    AND node_key ~ ('^' || v_prefix || '[0-9]+$');

  RETURN v_prefix || lpad(v_next::text, 4, '0');
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Write RPCs (public, SECURITY DEFINER -- the only client write path)
--    All take explicit tenant + product. Each write RPC establishes tenant
--    context internally (Decision 2):
--      PERFORM set_config('app.current_tenant_id', p_tenant::text, true)
--    so RLS WITH CHECK passes within the SAME transaction. PostgREST runs each
--    RPC in its own transaction, so a standalone set_config call would not
--    persist into a following RPC -- it must be set inside the RPC.
--
--    IMPORTANT: SECURITY DEFINER also BYPASSES RLS for the function owner, so
--    the set_config above is defense-in-depth (correct GUC for triggers /
--    future FORCE ROW LEVEL SECURITY), NOT the primary isolation. Tenant
--    isolation is enforced by EXPLICIT p_tenant filtering in every RPC below,
--    including the read RPCs in section 8.
-- ---------------------------------------------------------------------------

-- Upsert a node (insert new, or update a still-mutable one). Returns id.
CREATE OR REPLACE FUNCTION public.graph_upsert_node(
  p_tenant         UUID,
  p_product        TEXT,
  p_node_type      TEXT,
  p_node_key       TEXT,
  p_title          TEXT,
  p_status         TEXT,
  p_created_by     TEXT,
  p_kind           TEXT    DEFAULT NULL,
  p_blocking       BOOLEAN DEFAULT NULL,
  p_divergence     TEXT    DEFAULT NULL,
  p_maps_to_codebase TEXT[] DEFAULT '{}',
  p_aliases        TEXT[]  DEFAULT '{}',
  p_node_attributes JSONB  DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = product_graph, public
AS $$
DECLARE v_id UUID;
BEGIN
  PERFORM set_config('app.current_tenant_id', p_tenant::text, true);
  INSERT INTO product_graph.graph_nodes (
    tenant_id, product_key, node_type, node_key, title, status, created_by,
    kind, blocking, divergence, maps_to_codebase, aliases, node_attributes
  ) VALUES (
    p_tenant, p_product, p_node_type, p_node_key, p_title, p_status, p_created_by,
    p_kind, p_blocking, p_divergence, p_maps_to_codebase, p_aliases, p_node_attributes
  )
  ON CONFLICT (product_key, node_key) DO UPDATE SET
    title            = EXCLUDED.title,
    status           = EXCLUDED.status,
    kind             = EXCLUDED.kind,
    blocking         = EXCLUDED.blocking,
    divergence       = EXCLUDED.divergence,
    maps_to_codebase = EXCLUDED.maps_to_codebase,
    aliases          = EXCLUDED.aliases,
    node_attributes  = EXCLUDED.node_attributes
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

-- Add a typed edge by node_key endpoints. Idempotent on (type, src, dst).
CREATE OR REPLACE FUNCTION public.graph_add_edge(
  p_tenant     UUID,
  p_product    TEXT,
  p_edge_type  TEXT,
  p_src_key    TEXT,
  p_dst_key    TEXT,
  p_created_by TEXT,
  p_edge_attributes JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = product_graph, public
AS $$
DECLARE v_src UUID; v_dst UUID; v_id UUID;
BEGIN
  PERFORM set_config('app.current_tenant_id', p_tenant::text, true);
  SELECT id INTO v_src FROM product_graph.graph_nodes
    WHERE product_key = p_product AND node_key = p_src_key AND tenant_id = p_tenant;
  SELECT id INTO v_dst FROM product_graph.graph_nodes
    WHERE product_key = p_product AND node_key = p_dst_key AND tenant_id = p_tenant;
  IF v_src IS NULL OR v_dst IS NULL THEN
    RAISE EXCEPTION 'edge endpoint not found: % -> %', p_src_key, p_dst_key;
  END IF;

  INSERT INTO product_graph.graph_edges (
    tenant_id, product_key, edge_type, src_node_id, dst_node_id, created_by, edge_attributes
  ) VALUES (
    p_tenant, p_product, p_edge_type, v_src, v_dst, p_created_by, p_edge_attributes
  )
  ON CONFLICT (edge_type, src_node_id, dst_node_id) DO NOTHING
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

-- Ratify a knowledge-plane node (proposed -> accepted, with operator stamp).
CREATE OR REPLACE FUNCTION public.graph_ratify_node(
  p_tenant      UUID,
  p_product     TEXT,
  p_node_key    TEXT,
  p_new_status  TEXT,
  p_ratified_by TEXT
)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = product_graph, public
AS $$
BEGIN
  PERFORM set_config('app.current_tenant_id', p_tenant::text, true);
  UPDATE product_graph.graph_nodes
     SET status      = p_new_status,
         ratified_by = CASE WHEN p_new_status IN ('accepted','handed_off')
                            THEN p_ratified_by ELSE ratified_by END,
         ratified_at = CASE WHEN p_new_status IN ('accepted','handed_off')
                            THEN now() ELSE ratified_at END
   WHERE product_key = p_product AND node_key = p_node_key AND tenant_id = p_tenant;
END;
$$;

-- Concept resolution: find existing concept by canonical name or alias (anti-duplicate).
CREATE OR REPLACE FUNCTION public.graph_resolve_concept(
  p_tenant  UUID,
  p_product TEXT,
  p_noun    TEXT
)
RETURNS TABLE (node_key TEXT, title TEXT, status TEXT, kind TEXT, maps_to_codebase TEXT[])
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  -- Explicit tenant isolation: SECURITY DEFINER bypasses RLS for the owner.
  SELECT node_key, title, status, kind, maps_to_codebase
  FROM product_graph.graph_nodes
  WHERE node_type = 'concept'
    AND tenant_id = p_tenant
    AND product_key = p_product
    AND status <> 'rejected'
    AND (lower(title) = lower(p_noun) OR lower(p_noun) = ANY (SELECT lower(a) FROM unnest(aliases) a));
$$;

-- ---------------------------------------------------------------------------
-- 8. Read RPCs
-- ---------------------------------------------------------------------------

-- Full one-hop subgraph for a feature: the feature plus every node it links to
-- (questions raised, concepts referenced, decisions resolving its questions).
CREATE OR REPLACE FUNCTION public.graph_feature_subgraph(
  p_tenant      UUID,
  p_product     TEXT,
  p_feature_key TEXT
)
RETURNS TABLE (
  rel          TEXT,       -- 'self' | edge_type
  node_key     TEXT,
  node_type    TEXT,
  title        TEXT,
  status       TEXT,
  epistemic    TEXT,
  edge_attributes JSONB
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  WITH feat AS (
    SELECT id, node_key, node_type, title, status
    FROM product_graph.graph_nodes
    WHERE tenant_id = p_tenant AND product_key = p_product
      AND node_key = p_feature_key AND node_type = 'feature'
  )
  SELECT 'self', f.node_key, f.node_type, f.title, f.status,
         public.graph_node_epistemic_status(f.node_type, f.status), '{}'::jsonb
  FROM feat f
  UNION ALL
  SELECT e.edge_type, n.node_key, n.node_type, n.title, n.status,
         public.graph_node_epistemic_status(n.node_type, n.status), e.edge_attributes
  FROM feat f
  JOIN product_graph.graph_edges e ON (e.src_node_id = f.id OR e.dst_node_id = f.id)
  JOIN product_graph.graph_nodes n
    ON n.id = (CASE WHEN e.src_node_id = f.id THEN e.dst_node_id ELSE e.src_node_id END)
  WHERE n.id <> f.id;
$$;

-- Scope-readiness gate: derived, never stored. Returns the gate breakdown + verdict.
-- v1 gates: (1) no open blocking questions, (2) no referenced concept left 'rejected'/null,
--           (3) no open high-divergence questions. Contradiction check (gate 4) deferred.
CREATE OR REPLACE FUNCTION public.graph_feature_readiness(
  p_tenant      UUID,
  p_product     TEXT,
  p_feature_key TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  WITH feat AS (
    SELECT id FROM product_graph.graph_nodes
    WHERE tenant_id = p_tenant AND product_key = p_product
      AND node_key = p_feature_key AND node_type = 'feature'
  ),
  linked AS (
    SELECT DISTINCT n.*
    FROM feat f
    JOIN product_graph.graph_edges e ON (e.src_node_id = f.id OR e.dst_node_id = f.id)
    JOIN product_graph.graph_nodes n
      ON n.id = (CASE WHEN e.src_node_id = f.id THEN e.dst_node_id ELSE e.src_node_id END)
    WHERE n.id <> f.id
  ),
  g AS (
    SELECT
      COUNT(*) FILTER (WHERE node_type = 'question' AND status = 'open' AND blocking) AS open_blocking,
      COUNT(*) FILTER (WHERE node_type = 'question' AND status = 'open'
                         AND divergence = 'high') AS open_high_div,
      COUNT(*) FILTER (WHERE node_type = 'concept' AND status NOT IN ('accepted','proposed')) AS bad_concepts
    FROM linked
  )
  SELECT jsonb_build_object(
    'feature', p_feature_key,
    'gate_open_blocking_questions', (SELECT open_blocking FROM g),
    'gate_open_high_divergence',    (SELECT open_high_div FROM g),
    'gate_unresolved_concepts',     (SELECT bad_concepts FROM g),
    'gate_contradiction_check',     'deferred_v1',
    'scope_ready',
      ((SELECT open_blocking FROM g) = 0
       AND (SELECT open_high_div FROM g) = 0
       AND (SELECT bad_concepts FROM g) = 0)
  );
$$;

-- ---------------------------------------------------------------------------
-- 9. Governance registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version, deprecation_reason, rfc_reference
) VALUES
  ('product_graph.graph_nodes', NULL, 'active', '1.0.0',
   'BA Agent v1. Polymorphic graph nodes (feature/concept/question/decision). Rule/Attribute deferred.', 'RFC-BA-001'),
  ('product_graph.graph_edges', NULL, 'active', '1.0.0',
   'BA Agent v1. Typed edges (references/resolves/supersedes/derived_from).', 'RFC-BA-001');

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'product_graph';
-- SELECT proname FROM pg_proc WHERE proname LIKE 'graph_%';
-- SELECT public.graph_node_epistemic_status('decision','accepted');  -- 'fact'
-- SELECT public.graph_node_epistemic_status('decision','proposed');  -- 'claim'
