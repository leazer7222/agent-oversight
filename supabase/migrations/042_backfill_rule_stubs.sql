-- Migration 042: Backfill Decision.implies_rules[] stubs into first-class Rule nodes (P2, step 2)
--
-- For each Decision carrying implies_rules[], mint a proposed RULE-* node per statement, link
-- Decision --establishes--> Rule, and cite the SAME Concepts the Decision references
-- (Rule --references--> Concept) so the rule satisfies the "must cite >=1 concept" invariant.
--
-- Never edits the (frozen) Decisions; the implies_rules stub is retained as historical provenance.
-- Idempotent: a Decision that already establishes a Rule is skipped, so re-running is a no-op.
-- Uses the same RPCs as the runtime (key minting, RLS, trigger behave identically).
--
-- implies_attributes[] backfill is omitted: zero exist today, and the forward BA promotion path
-- (dashboard answer route) handles attributes for new Decisions.
--
-- Plan: docs/p2-rule-attribute-gate-a-plan.md (sections 4, 13). Depends on: 039.

DO $$
DECLARE
  d         RECORD;
  v_stmt    TEXT;
  v_rulekey TEXT;
  v_concept TEXT;
BEGIN
  FOR d IN
    SELECT n.id, n.tenant_id, n.product_key, n.node_key,
           n.node_attributes->'implies_rules' AS rules
    FROM product_graph.graph_nodes n
    WHERE n.node_type = 'decision'
      AND jsonb_array_length(COALESCE(n.node_attributes->'implies_rules','[]'::jsonb)) > 0
      AND NOT EXISTS (                                  -- idempotency: already promoted?
        SELECT 1 FROM product_graph.graph_edges e
        JOIN product_graph.graph_nodes rn ON rn.id = e.dst_node_id
        WHERE e.src_node_id = n.id AND e.edge_type = 'establishes' AND rn.node_type = 'rule')
  LOOP
    FOR v_stmt IN SELECT jsonb_array_elements_text(d.rules)
    LOOP
      v_rulekey := public.graph_next_key(d.product_key, 'rule');

      PERFORM public.graph_upsert_node(
        p_tenant          => d.tenant_id,
        p_product         => d.product_key,
        p_node_type       => 'rule',
        p_node_key        => v_rulekey,
        p_title           => left(v_stmt, 80),
        p_status          => 'proposed',
        p_created_by      => 'backfill-042',
        p_node_attributes => jsonb_build_object(
                               'statement', v_stmt,
                               'normative_force', 'must',
                               'backfilled_from', d.node_key));

      PERFORM public.graph_add_edge(
        p_tenant => d.tenant_id, p_product => d.product_key, p_edge_type => 'establishes',
        p_src_key => d.node_key, p_dst_key => v_rulekey, p_created_by => 'backfill-042',
        p_edge_attributes => '{}'::jsonb);

      FOR v_concept IN
        SELECT cn.node_key
        FROM product_graph.graph_edges ce
        JOIN product_graph.graph_nodes cn ON cn.id = ce.dst_node_id
        WHERE ce.src_node_id = d.id AND ce.edge_type = 'references' AND cn.node_type = 'concept'
      LOOP
        PERFORM public.graph_add_edge(
          p_tenant => d.tenant_id, p_product => d.product_key, p_edge_type => 'references',
          p_src_key => v_rulekey, p_dst_key => v_concept, p_created_by => 'backfill-042',
          p_edge_attributes => '{}'::jsonb);
      END LOOP;

    END LOOP;
  END LOOP;
END $$;
