-- Migration 032: list features for the Scoping dashboard index.
-- SECURITY DEFINER + explicit tenant filter. Apply to hdhovyrlnfojtkqbcegh. Depends on 024.

CREATE OR REPLACE FUNCTION public.graph_list_features(
  p_tenant  UUID,
  p_product TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  SELECT COALESCE(jsonb_agg(jsonb_build_object(
    'node_key', node_key, 'title', title, 'status', status, 'created_at', created_at
  ) ORDER BY created_at DESC), '[]'::jsonb)
  FROM product_graph.graph_nodes
  WHERE tenant_id = p_tenant AND product_key = p_product AND node_type = 'feature';
$$;
