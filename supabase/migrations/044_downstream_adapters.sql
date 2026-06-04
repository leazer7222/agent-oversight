-- Migration 044: downstream stage adapters (P2, step 5)
--
-- Read-time projections over public.graph_feature_graph (single traversal source of truth), each
-- filtered to one downstream stage's slice. Downstream agents (UX / Engineering / QA) consume these
-- graph-backed projections, NEVER the rendered Feature Spec prose. Accepted nodes are frozen by
-- trigger, so a live read equals the pinned snapshot for ratified content (snapshot-id pinning can be
-- layered on later without changing these signatures).
--
-- Plan: docs/p2-rule-attribute-gate-a-plan.md (section 12). Depends on: 040.

-- ---------------------------------------------------------------------------
-- Engineering: everything needed to build - rules, attributes, concepts (+ codebase maps via the
-- node rows), rejected alternatives, and the full edge set.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.graph_adapter_eng(
  p_tenant UUID, p_product TEXT, p_feature_key TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  WITH g AS (SELECT public.graph_feature_graph(p_tenant, p_product, p_feature_key) AS j),
  n AS (SELECT jsonb_array_elements((SELECT j->'nodes' FROM g)) AS node)
  SELECT jsonb_build_object(
    'stage', 'engineering',
    'feature', (SELECT j->'feature' FROM g),
    'concepts',           COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='concept'), '[]'::jsonb),
    'rules',              COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='rule'), '[]'::jsonb),
    'attributes',         COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='attribute'), '[]'::jsonb),
    'accepted_decisions', COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='decision' AND node->>'status'='accepted'), '[]'::jsonb),
    'rejected_decisions', COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='decision' AND node->>'status'='rejected'), '[]'::jsonb),
    'edges', (SELECT j->'edges' FROM g)
  );
$$;

-- ---------------------------------------------------------------------------
-- UX: actors, concepts, UX-behavior rules, attributes, accepted decisions, open questions.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.graph_adapter_ux(
  p_tenant UUID, p_product TEXT, p_feature_key TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  WITH g AS (SELECT public.graph_feature_graph(p_tenant, p_product, p_feature_key) AS j),
  n AS (SELECT jsonb_array_elements((SELECT j->'nodes' FROM g)) AS node)
  SELECT jsonb_build_object(
    'stage', 'ux',
    'feature', (SELECT j->'feature' FROM g),
    'actors',            COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='concept' AND node->>'kind'='actor'), '[]'::jsonb),
    'concepts',          COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='concept'), '[]'::jsonb),
    'ux_rules',          COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='rule' AND node->>'kind'='ux_behavior'), '[]'::jsonb),
    'attributes',        COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='attribute'), '[]'::jsonb),
    'accepted_decisions',COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='decision' AND node->>'status'='accepted'), '[]'::jsonb),
    'open_questions',    COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='question' AND node->>'status'='open'), '[]'::jsonb)
  );
$$;

-- ---------------------------------------------------------------------------
-- QA: rules (acceptance criteria are derived from these), attributes (validation targets),
-- rejected alternatives, and the edge set (to trace rule -> concept / rule -> attribute).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.graph_adapter_qa(
  p_tenant UUID, p_product TEXT, p_feature_key TEXT
)
RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = product_graph, public
AS $$
  WITH g AS (SELECT public.graph_feature_graph(p_tenant, p_product, p_feature_key) AS j),
  n AS (SELECT jsonb_array_elements((SELECT j->'nodes' FROM g)) AS node)
  SELECT jsonb_build_object(
    'stage', 'qa',
    'feature', (SELECT j->'feature' FROM g),
    'rules',              COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='rule'), '[]'::jsonb),
    'attributes',         COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='attribute'), '[]'::jsonb),
    'rejected_decisions', COALESCE((SELECT jsonb_agg(node) FROM n WHERE node->>'node_type'='decision' AND node->>'status'='rejected'), '[]'::jsonb),
    'edges', (SELECT j->'edges' FROM g)
  );
$$;
