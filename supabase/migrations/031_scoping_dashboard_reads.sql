-- Migration 031: read RPCs for the Scoping dashboard
--   graph_feature_detail(tenant, product, feature_key) -> full feature subgraph (nodes + edges) as jsonb
--   graph_backlog(tenant, product)                      -> ratification backlog health metric
--
-- Both SECURITY DEFINER with explicit tenant filtering (SECURITY DEFINER bypasses RLS for the owner).
-- Apply to project: hdhovyrlnfojtkqbcegh. Depends on: 024, 030.

CREATE OR REPLACE FUNCTION public.graph_feature_detail(
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
  linked AS (
    SELECT DISTINCT n.*
    FROM feat f
    JOIN product_graph.graph_edges e ON (e.src_node_id = f.id OR e.dst_node_id = f.id)
    JOIN product_graph.graph_nodes n
      ON n.id = (CASE WHEN e.src_node_id = f.id THEN e.dst_node_id ELSE e.src_node_id END)
    WHERE n.id <> f.id
  ),
  allnodes AS (SELECT * FROM feat UNION SELECT * FROM linked),
  fe AS (
    SELECT e.* FROM product_graph.graph_edges e
    JOIN feat f ON (e.src_node_id = f.id OR e.dst_node_id = f.id)
  )
  SELECT jsonb_build_object(
    'feature', (SELECT to_jsonb(f) FROM feat f),
    'nodes', COALESCE((SELECT jsonb_agg(to_jsonb(n) ORDER BY n.node_key) FROM allnodes n), '[]'::jsonb),
    'edges', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'edge_type', e.edge_type,
        'src', (SELECT node_key FROM product_graph.graph_nodes WHERE id = e.src_node_id),
        'dst', (SELECT node_key FROM product_graph.graph_nodes WHERE id = e.dst_node_id),
        'edge_attributes', e.edge_attributes)) FROM fe e), '[]'::jsonb)
  );
$$;

CREATE OR REPLACE FUNCTION public.graph_backlog(
  p_tenant  UUID,
  p_product TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  SELECT jsonb_build_object(
    'proposed_concepts',  COUNT(*) FILTER (WHERE node_type = 'concept'  AND status = 'proposed'),
    'proposed_decisions', COUNT(*) FILTER (WHERE node_type = 'decision' AND status = 'proposed'),
    'oldest_proposed_at', MIN(created_at) FILTER (WHERE status = 'proposed' AND node_type IN ('concept','decision'))
  )
  FROM product_graph.graph_nodes
  WHERE tenant_id = p_tenant AND product_key = p_product;
$$;
