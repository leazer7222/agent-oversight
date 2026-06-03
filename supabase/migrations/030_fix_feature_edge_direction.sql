-- Migration 030: fix graph_feature_readiness / graph_feature_subgraph edge direction
--
-- Bug: both functions gathered "linked" nodes only via edges where the FEATURE is the
-- source (references: FEAT -> CON). But Questions link via derived_from with the QUESTION
-- as source (QST -> FEAT), so open blocking questions were invisible to the readiness gate
-- (scope_ready returned true even with blocking questions open). Fix: traverse edges in
-- BOTH directions relative to the feature.
--
-- Supersedes the function bodies in 024 (which is amended to match for fresh applies).
-- Apply to project: hdhovyrlnfojtkqbcegh. Depends on: 024_product_graph_phase1.sql.

CREATE OR REPLACE FUNCTION public.graph_feature_subgraph(
  p_tenant      UUID,
  p_product     TEXT,
  p_feature_key TEXT
)
RETURNS TABLE (
  rel          TEXT,
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
