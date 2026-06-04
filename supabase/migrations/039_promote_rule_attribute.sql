-- Migration 039: Promote Rule + Attribute to first-class node types (P2, step 1)
--
-- Additive extension of the polymorphic product_graph.graph_nodes / graph_edges model.
-- Adds node_type 'rule' and 'attribute', edge_type 'establishes' and 'owns', and relaxes the
-- concept-only constraints on `kind` and `maps_to_codebase` so rules/attributes can carry them.
-- No data writes. Existing rows/types remain valid. Constraint relaxations only widen what is allowed.
--
-- Plan: docs/p2-rule-attribute-gate-a-plan.md (section 4). Apply to hdhovyrlnfojtkqbcegh.
-- Depends on: 024_product_graph_phase1.sql.

-- ---------------------------------------------------------------------------
-- 1. node_type: add 'rule', 'attribute'
-- ---------------------------------------------------------------------------
ALTER TABLE product_graph.graph_nodes DROP CONSTRAINT IF EXISTS graph_nodes_node_type_check;
ALTER TABLE product_graph.graph_nodes
  ADD CONSTRAINT ck_node_type CHECK (
    node_type IN ('feature','concept','question','decision','rule','attribute')
  );

-- ---------------------------------------------------------------------------
-- 2. node_key prefix: add RULE-* and ATR-*
-- ---------------------------------------------------------------------------
ALTER TABLE product_graph.graph_nodes DROP CONSTRAINT IF EXISTS ck_node_key_prefix;
ALTER TABLE product_graph.graph_nodes
  ADD CONSTRAINT ck_node_key_prefix CHECK (
    (node_type = 'feature'   AND node_key LIKE 'FEAT-%') OR
    (node_type = 'concept'   AND node_key LIKE 'CON-%')  OR
    (node_type = 'question'  AND node_key LIKE 'QST-%')  OR
    (node_type = 'decision'  AND node_key LIKE 'DEC-%')  OR
    (node_type = 'rule'      AND node_key LIKE 'RULE-%') OR
    (node_type = 'attribute' AND node_key LIKE 'ATR-%')
  );

-- ---------------------------------------------------------------------------
-- 3. per-type lifecycle: full status sets (closed CHECK; enumerate now)
--    rule:      proposed -> accepted | rejected | superseded
--    attribute: proposed -> accepted | rejected | superseded | deprecated (follows owning concept)
-- ---------------------------------------------------------------------------
ALTER TABLE product_graph.graph_nodes DROP CONSTRAINT IF EXISTS ck_node_status;
ALTER TABLE product_graph.graph_nodes
  ADD CONSTRAINT ck_node_status CHECK (
    (node_type = 'feature'   AND status IN ('scoping','ready','handed_off','shelved')) OR
    (node_type = 'concept'   AND status IN ('proposed','accepted','rejected','deprecated')) OR
    (node_type = 'question'  AND status IN ('open','answered','deferred')) OR
    (node_type = 'decision'  AND status IN ('proposed','accepted','rejected','superseded')) OR
    (node_type = 'rule'      AND status IN ('proposed','accepted','rejected','superseded')) OR
    (node_type = 'attribute' AND status IN ('proposed','accepted','rejected','superseded','deprecated'))
  );

-- ---------------------------------------------------------------------------
-- 4. relax `kind`: allowed on concept, rule, attribute (open vocab: rule_type / attribute_type)
-- ---------------------------------------------------------------------------
ALTER TABLE product_graph.graph_nodes DROP CONSTRAINT IF EXISTS ck_kind_concept_only;
ALTER TABLE product_graph.graph_nodes
  ADD CONSTRAINT ck_kind_allowed CHECK (
    kind IS NULL OR node_type IN ('concept','rule','attribute')
  );

-- ---------------------------------------------------------------------------
-- 5. split the bundled mapping constraint:
--    aliases stays concept-only; maps_to_codebase widens to concept | rule | attribute.
-- ---------------------------------------------------------------------------
ALTER TABLE product_graph.graph_nodes DROP CONSTRAINT IF EXISTS ck_mapping_concept_only;
ALTER TABLE product_graph.graph_nodes
  ADD CONSTRAINT ck_aliases_concept_only CHECK (
    aliases = '{}'::text[] OR node_type = 'concept'
  );
ALTER TABLE product_graph.graph_nodes
  ADD CONSTRAINT ck_maps_codebase_scope CHECK (
    maps_to_codebase = '{}'::text[] OR node_type IN ('concept','rule','attribute')
  );

-- ---------------------------------------------------------------------------
-- 6. edge_type: add 'establishes' (decision -> rule|attribute) and 'owns' (concept -> attribute)
-- ---------------------------------------------------------------------------
ALTER TABLE product_graph.graph_edges DROP CONSTRAINT IF EXISTS graph_edges_edge_type_check;
ALTER TABLE product_graph.graph_edges
  ADD CONSTRAINT ck_edge_type CHECK (
    edge_type IN ('references','resolves','supersedes','derived_from','establishes','owns')
  );

-- ---------------------------------------------------------------------------
-- 7. graph_next_key: mint RULE-* and ATR-*
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
    WHEN 'feature'   THEN 'FEAT-'
    WHEN 'concept'   THEN 'CON-'
    WHEN 'question'  THEN 'QST-'
    WHEN 'decision'  THEN 'DEC-'
    WHEN 'rule'      THEN 'RULE-'
    WHEN 'attribute' THEN 'ATR-'
    ELSE NULL
  END;
  IF v_prefix IS NULL THEN
    RAISE EXCEPTION 'graph_next_key: unknown node_type %', p_node_type;
  END IF;

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
-- 8. governance registry
-- ---------------------------------------------------------------------------
INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version, deprecation_reason, rfc_reference
) VALUES
  ('product_graph.graph_nodes', 'node_type:rule', 'active', '1.1.0',
   'P2: Rule promoted to first-class node type.', 'RFC-BA-002'),
  ('product_graph.graph_nodes', 'node_type:attribute', 'active', '1.1.0',
   'P2: Attribute promoted to first-class node type (concept-owned, non-sovereign).', 'RFC-BA-002');

-- ---------------------------------------------------------------------------
-- Verification (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT public.graph_next_key('reformai-product','rule');       -- RULE-0001
-- SELECT public.graph_next_key('reformai-product','attribute');  -- ATR-0001
-- SELECT conname FROM pg_constraint WHERE conrelid='product_graph.graph_nodes'::regclass AND contype='c';
