-- Migration 038: graph_set_maps_to_codebase - targeted backfill of a concept's code links
--
-- The BA reuses existing Concepts across features (graph_resolve_concept). When a Concept was
-- minted net-new in an earlier run that failed to populate maps_to_codebase (the Partner/Admin
-- bug), reuse must be able to backfill the code link WITHOUT clobbering other fields.
-- graph_upsert_node's ON CONFLICT overwrites aliases/node_attributes from defaults, so it is NOT
-- safe for a partial update. This updates ONLY maps_to_codebase (+ updated_at), preserving
-- title/status/kind/aliases/node_attributes/ratified_*.
--
-- Apply to project: hdhovyrlnfojtkqbcegh

CREATE OR REPLACE FUNCTION public.graph_set_maps_to_codebase(
  p_tenant  UUID,
  p_product TEXT,
  p_node_key TEXT,
  p_cbc_ids TEXT[]
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = product_graph, public
AS $$
DECLARE v_id UUID;
BEGIN
  PERFORM set_config('app.current_tenant_id', p_tenant::text, true);
  UPDATE product_graph.graph_nodes
     SET maps_to_codebase = p_cbc_ids,
         updated_at = now()
   WHERE tenant_id = p_tenant
     AND product_key = p_product
     AND node_key = p_node_key
     AND node_type = 'concept'
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.graph_set_maps_to_codebase(UUID, TEXT, TEXT, TEXT[]) IS
  'Targeted update of a concept''s maps_to_codebase only (preserves all other fields). Used by the '
  'BA to backfill code links onto reused concepts that were minted without them.';
