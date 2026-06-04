-- Migration 040: transitive feature subgraph read (P2, step 3)
--
-- Replaces the one-hop graph_feature_detail (which could not even see Decisions, let alone Rules at
-- 3 hops). Uses a TYPED, fixed-shape traversal rather than naive undirected BFS, so a shared Concept
-- never bleeds in OTHER features' decisions/rules:
--
--   feature
--     <-derived_from-  question
--                        <-resolves-  decision
--                                       -establishes->  rule | attribute
--   concept  =  referenced by (feature | decision | rule)
--   attribute = owned by (one of those concepts) OR established by (one of those decisions)
--
-- We never follow INCOMING references into a Concept, so shared Concepts act as leaves (plus their
-- owned Attributes). SECURITY DEFINER + explicit tenant filter (RLS-bypass rule).
--
-- Plan: docs/p2-rule-attribute-gate-a-plan.md (section 7). Depends on: 024, 039.

CREATE OR REPLACE FUNCTION public.graph_feature_graph(
  p_tenant      UUID,
  p_product     TEXT,
  p_feature_key TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  WITH feat AS (
    SELECT * FROM product_graph.graph_nodes
    WHERE tenant_id = p_tenant AND product_key = p_product
      AND node_key = p_feature_key AND node_type = 'feature'
  ),
  q AS (  -- questions derived_from the feature
    SELECT n.* FROM feat f
    JOIN product_graph.graph_edges e ON e.dst_node_id = f.id AND e.edge_type = 'derived_from'
    JOIN product_graph.graph_nodes n ON n.id = e.src_node_id AND n.node_type = 'question'
  ),
  d AS (  -- decisions resolving those questions
    SELECT DISTINCT n.* FROM q
    JOIN product_graph.graph_edges e ON e.dst_node_id = q.id AND e.edge_type = 'resolves'
    JOIN product_graph.graph_nodes n ON n.id = e.src_node_id AND n.node_type = 'decision'
  ),
  r AS (  -- rules established by those decisions
    SELECT DISTINCT n.* FROM d
    JOIN product_graph.graph_edges e ON e.src_node_id = d.id AND e.edge_type = 'establishes'
    JOIN product_graph.graph_nodes n ON n.id = e.dst_node_id AND n.node_type = 'rule'
  ),
  con AS (  -- concepts referenced by feature, decisions, or rules
    SELECT DISTINCT n.* FROM product_graph.graph_edges e
    JOIN product_graph.graph_nodes n ON n.id = e.dst_node_id AND n.node_type = 'concept'
    WHERE e.edge_type = 'references'
      AND e.src_node_id IN (
        SELECT id FROM feat UNION SELECT id FROM d UNION SELECT id FROM r)
  ),
  att AS (  -- attributes owned by those concepts OR established by those decisions
    SELECT DISTINCT n.* FROM product_graph.graph_edges e
    JOIN product_graph.graph_nodes n ON n.id = e.dst_node_id AND n.node_type = 'attribute'
    WHERE (e.edge_type = 'owns'        AND e.src_node_id IN (SELECT id FROM con))
       OR (e.edge_type = 'establishes' AND e.src_node_id IN (SELECT id FROM d))
  ),
  allnodes AS (
    SELECT * FROM feat UNION SELECT * FROM q UNION SELECT * FROM d
    UNION SELECT * FROM r UNION SELECT * FROM con UNION SELECT * FROM att
  ),
  alledges AS (
    SELECT e.* FROM product_graph.graph_edges e
    WHERE e.src_node_id IN (SELECT id FROM allnodes)
      AND e.dst_node_id IN (SELECT id FROM allnodes)
  )
  SELECT jsonb_build_object(
    'feature', (SELECT to_jsonb(f) FROM feat f),
    'nodes', COALESCE((SELECT jsonb_agg(to_jsonb(n) ORDER BY n.node_key) FROM allnodes n), '[]'::jsonb),
    'edges', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'edge_type', e.edge_type,
        'src', (SELECT node_key FROM product_graph.graph_nodes WHERE id = e.src_node_id),
        'dst', (SELECT node_key FROM product_graph.graph_nodes WHERE id = e.dst_node_id),
        'edge_attributes', e.edge_attributes)) FROM alledges e), '[]'::jsonb)
  );
$$;
