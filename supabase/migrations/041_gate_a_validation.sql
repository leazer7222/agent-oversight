-- Migration 041: Gate A validation + snapshot output type (P2, step 4, Option B - self-contained)
--
-- Adds output_type 'gate_a_feature_spec' (immutable snapshot row in agent_outputs) and the
-- graph_gate_a_readiness validation RPC. Gate A validation is STRICTLY STRONGER than
-- graph_feature_readiness: it requires the knowledge nodes to be ratified (not proposed), rules to be
-- promoted + cited, attributes to be owned, and codebase mappings to resolve in the cbc registry.
--
-- Does NOT apply the feature_lifecycle spine (migration 026) - the snapshot is self-contained in
-- agent_outputs. Plan: docs/p2-rule-attribute-gate-a-plan.md (sections 4, 5, 9). Depends on: 039, 040.

-- ---------------------------------------------------------------------------
-- 1. agent_outputs.output_type += 'gate_a_feature_spec'
-- ---------------------------------------------------------------------------
ALTER TABLE public.agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;
ALTER TABLE public.agent_outputs
  ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type = ANY (ARRAY[
    'marketing_brief'::text, 'lp_blueprint'::text, 'strategy_summary'::text, 'context_snapshot'::text,
    'ui_components'::text, 'code_review'::text, 'codebase_context'::text, 'product_graph_scope'::text,
    'intake_assessment'::text, 'clarification_brief'::text, 'concept_resolution'::text,
    'gate_a_feature_spec'::text, 'other'::text
  ]));

-- ---------------------------------------------------------------------------
-- 2. graph_gate_a_readiness - hard failures (H1-H7) + warnings (W4). Same typed traversal as 040.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.graph_gate_a_readiness(
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
  q AS (
    SELECT n.* FROM feat f
    JOIN product_graph.graph_edges e ON e.dst_node_id = f.id AND e.edge_type = 'derived_from'
    JOIN product_graph.graph_nodes n ON n.id = e.src_node_id AND n.node_type = 'question'
  ),
  d AS (
    SELECT DISTINCT n.* FROM q
    JOIN product_graph.graph_edges e ON e.dst_node_id = q.id AND e.edge_type = 'resolves'
    JOIN product_graph.graph_nodes n ON n.id = e.src_node_id AND n.node_type = 'decision'
  ),
  r AS (
    SELECT DISTINCT n.* FROM d
    JOIN product_graph.graph_edges e ON e.src_node_id = d.id AND e.edge_type = 'establishes'
    JOIN product_graph.graph_nodes n ON n.id = e.dst_node_id AND n.node_type = 'rule'
  ),
  con AS (
    SELECT DISTINCT n.* FROM product_graph.graph_edges e
    JOIN product_graph.graph_nodes n ON n.id = e.dst_node_id AND n.node_type = 'concept'
    WHERE e.edge_type = 'references'
      AND e.src_node_id IN (SELECT id FROM feat UNION SELECT id FROM d UNION SELECT id FROM r)
  ),
  att AS (
    SELECT DISTINCT n.* FROM product_graph.graph_edges e
    JOIN product_graph.graph_nodes n ON n.id = e.dst_node_id AND n.node_type = 'attribute'
    WHERE (e.edge_type = 'owns'        AND e.src_node_id IN (SELECT id FROM con))
       OR (e.edge_type = 'establishes' AND e.src_node_id IN (SELECT id FROM d))
  ),
  checks AS (
    SELECT 'H1' AS code,
      (SELECT count(*) FROM q WHERE status='open' AND blocking) AS cnt,
      'open blocking question(s)' AS msg
    UNION ALL SELECT 'H2',
      (SELECT count(*) FROM (
         SELECT status FROM con UNION ALL SELECT status FROM d
         UNION ALL SELECT status FROM r UNION ALL SELECT status FROM att) k
       WHERE k.status = 'proposed'),
      'unratified (proposed) knowledge node(s)'
    UNION ALL SELECT 'H3',
      (SELECT count(*) FROM d
       WHERE jsonb_array_length(COALESCE(d.node_attributes->'implies_rules','[]'::jsonb)) > 0
         AND NOT EXISTS (SELECT 1 FROM product_graph.graph_edges e JOIN r rr ON rr.id=e.dst_node_id
                         WHERE e.src_node_id=d.id AND e.edge_type='establishes')),
      'accepted decision(s) with un-promoted implies_rules stub'
    UNION ALL SELECT 'H4',
      (SELECT count(*) FROM r
       WHERE NOT EXISTS (SELECT 1 FROM product_graph.graph_edges e JOIN con cc ON cc.id=e.dst_node_id
                         WHERE e.src_node_id=r.id AND e.edge_type='references')),
      'rule(s) citing no concept'
    UNION ALL SELECT 'H5',
      (SELECT count(*) FROM att a
       WHERE (SELECT count(*) FROM product_graph.graph_edges e
              WHERE e.dst_node_id=a.id AND e.edge_type='owns') <> 1),
      'attribute(s) without exactly one owner'
    UNION ALL SELECT 'H6',
      (SELECT count(*) FROM (
         SELECT unnest(maps_to_codebase) cid FROM con
         UNION ALL SELECT unnest(maps_to_codebase) FROM r
         UNION ALL SELECT unnest(maps_to_codebase) FROM att) m
       WHERE NOT EXISTS (SELECT 1 FROM platform.cbc_identity_registry reg WHERE reg.cbc_id=m.cid)),
      'maps_to_codebase value(s) not in cbc registry'
    UNION ALL SELECT 'H7',
      (SELECT count(*) FROM feat WHERE NOT (node_attributes ? 'scoped_against_commit')),
      'feature missing scoped_against_commit provenance'
  ),
  warns AS (
    SELECT 'W4' AS code,
      (SELECT count(*) FROM q WHERE status='open' AND NOT blocking) AS cnt,
      'non-blocking open question(s)' AS msg
  )
  SELECT jsonb_build_object(
    'feature', p_feature_key,
    'hard_failures', COALESCE((SELECT jsonb_agg(format('%s: %s %s', code, cnt, msg) ORDER BY code)
                               FROM checks WHERE cnt > 0), '[]'::jsonb),
    'warnings', COALESCE((SELECT jsonb_agg(format('%s: %s %s', code, cnt, msg) ORDER BY code)
                          FROM warns WHERE cnt > 0), '[]'::jsonb),
    'status', CASE
      WHEN EXISTS (SELECT 1 FROM checks WHERE cnt > 0) THEN 'blocked'
      WHEN EXISTS (SELECT 1 FROM warns  WHERE cnt > 0) THEN 'warn'
      ELSE 'ready' END
  );
$$;
