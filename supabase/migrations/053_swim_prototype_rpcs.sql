-- Migration 053: swim_sourcing prototype RPC surface
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 049 (schema), 050 (queue + facility RPCs)
-- Status: AUTHORED 2026-10-20 for the pool-acquisition prototype.
--
-- WHY THIS EXISTS. PostgREST exposes only `public` and `graphql_public` on
-- this project (verified live: a .schema('swim_sourcing') call returns
-- PGRST106). Every read or write of a swim_sourcing row from the app or the
-- worker therefore has to go through a SECURITY DEFINER function in `public`,
-- which is the pattern 050 already establishes. This file adds the functions
-- the prototype needs for enrichment, drafting, simulated inbound mail,
-- classification, and the dashboard reads.
--
-- SCOPE RULES, deliberately narrow:
--   * No new tables. One additive nullable column (outreach_threads.last_classification).
--   * No CHECK constraint is altered. Four-state triage rides inside
--     qualifications.score_breakdown until MVP 1 promotes it to a column.
--   * Nothing here can send anything. There is no send function.
--   * Every function is service_role only, like 050.
--
-- Prototype labelling: drafts are written with provider='mock' (an existing
-- CHECK value), simulated inbound mail must arrive with a '[SIMULATED]' subject
-- prefix (enforced below), and fixture facilities carry source='fixture'.

BEGIN;

-- ===========================================================================
-- Additive column: the latest classification verdict for a thread
-- ===========================================================================
ALTER TABLE swim_sourcing.outreach_threads
  ADD COLUMN IF NOT EXISTS last_classification JSONB;

-- ===========================================================================
-- Facility attributes: now also returns contacts and the latest qualification,
-- so a handler needs one read per facility rather than three.
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.swim_facility_attributes(p_facility_id UUID)
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT jsonb_build_object(
    'facility_id', f.id,
    'company_id', f.company_id,
    'name', f.name,
    'facility_type', f.facility_type,
    'website', f.website,
    'phone', f.phone,
    'source', f.source,
    'source_ref', f.source_ref,
    'source_url', f.source_url,
    'distance_miles', f.distance_miles,
    'pipeline_stage', f.pipeline_stage,
    'attributes', f.attributes,
    'attributes_confidence', f.attributes_confidence,
    'unknown_fields', to_jsonb(f.unknown_fields),
    'contacts', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'contact_id', c.id, 'full_name', c.full_name, 'role_title', c.role_title,
        'email', c.email, 'phone', c.phone, 'confidence', c.confidence,
        'source_url', c.source_url, 'evidence_snippet', c.evidence_snippet,
        'is_primary', c.is_primary) ORDER BY c.is_primary DESC, c.created_at)
      FROM swim_sourcing.facility_contacts c WHERE c.facility_id = f.id), '[]'::jsonb),
    'latest_qualification', (
      SELECT jsonb_build_object(
        'qualification_id', q.id, 'status', q.status, 'score', q.score,
        'completeness', q.completeness, 'score_breakdown', q.score_breakdown,
        'open_questions', q.open_questions, 'disqualifiers', to_jsonb(q.disqualifiers),
        'created_at', q.created_at)
      FROM swim_sourcing.qualifications q
      WHERE q.facility_id = f.id ORDER BY q.created_at DESC LIMIT 1))
  FROM swim_sourcing.facilities f WHERE f.id = p_facility_id;
$$;

-- ===========================================================================
-- Enrichment: merge evidence-backed attributes into a facility
-- ===========================================================================
-- p_payload: { facility_id, attributes {k: v}, attributes_confidence {k: 'verified'|'inferred'} }
-- Keys present in attributes leave unknown_fields. Never removes an existing
-- attribute; a later thinner extraction cannot erase an earlier fact.
CREATE OR REPLACE FUNCTION public.swim_apply_enrichment(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_facility UUID := (p_payload->>'facility_id')::uuid;
  v_attrs    JSONB := coalesce(p_payload->'attributes', '{}'::jsonb);
  v_conf     JSONB := coalesce(p_payload->'attributes_confidence', '{}'::jsonb);
  v_out      JSONB;
BEGIN
  IF v_facility IS NULL THEN
    RAISE EXCEPTION 'facility_id is required';
  END IF;

  UPDATE swim_sourcing.facilities f
     SET attributes            = f.attributes || v_attrs,
         attributes_confidence = f.attributes_confidence || v_conf,
         unknown_fields        = ARRAY(SELECT u FROM unnest(f.unknown_fields) u
                                       WHERE NOT ((f.attributes || v_attrs) ? u)),
         source_fetched_at     = now(),
         updated_at            = now()
   WHERE f.id = v_facility AND f.company_id = p_company_id
   RETURNING jsonb_build_object(
     'facility_id', f.id,
     'attributes', f.attributes,
     'attributes_confidence', f.attributes_confidence,
     'unknown_fields', to_jsonb(f.unknown_fields)) INTO v_out;

  IF v_out IS NULL THEN
    RAISE EXCEPTION 'facility % not found for company %', v_facility, p_company_id;
  END IF;
  RETURN v_out;
END $$;

-- ===========================================================================
-- Contacts: insert with mandatory on-page evidence
-- ===========================================================================
-- p_payload: { facility_id, full_name, role_title, email, phone, confidence,
--              source_url, evidence_snippet, is_primary }
-- The NOT NULL columns already refuse a contact without source_url or
-- evidence_snippet; this function makes the refusal explicit and idempotent.
CREATE OR REPLACE FUNCTION public.swim_record_contact(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_facility UUID := (p_payload->>'facility_id')::uuid;
  v_email    TEXT := nullif(trim(p_payload->>'email'), '');
  v_id       UUID;
BEGIN
  IF coalesce(p_payload->>'source_url', '') = '' OR coalesce(p_payload->>'evidence_snippet', '') = '' THEN
    RAISE EXCEPTION 'a contact requires source_url and evidence_snippet (no evidence, no row)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM swim_sourcing.facilities WHERE id = v_facility AND company_id = p_company_id) THEN
    RAISE EXCEPTION 'facility % not found for company %', v_facility, p_company_id;
  END IF;

  -- Idempotency: email is the strong key; otherwise name + phone.
  IF v_email IS NOT NULL THEN
    SELECT id INTO v_id FROM swim_sourcing.facility_contacts
     WHERE facility_id = v_facility AND lower(email) = lower(v_email);
  ELSE
    SELECT id INTO v_id FROM swim_sourcing.facility_contacts
     WHERE facility_id = v_facility AND email IS NULL
       AND lower(coalesce(full_name, '')) = lower(coalesce(p_payload->>'full_name', ''))
       AND coalesce(phone, '') = coalesce(p_payload->>'phone', '');
  END IF;

  IF v_id IS NOT NULL THEN
    UPDATE swim_sourcing.facility_contacts
       SET role_title = coalesce(p_payload->>'role_title', role_title),
           phone      = coalesce(p_payload->>'phone', phone),
           confidence = coalesce(p_payload->>'confidence', confidence),
           source_url = p_payload->>'source_url',
           evidence_snippet = p_payload->>'evidence_snippet'
     WHERE id = v_id;
    RETURN v_id;
  END IF;

  INSERT INTO swim_sourcing.facility_contacts (
    company_id, facility_id, full_name, role_title, email, phone, confidence,
    source_url, evidence_snippet, is_primary)
  VALUES (
    p_company_id, v_facility, p_payload->>'full_name', p_payload->>'role_title',
    v_email, p_payload->>'phone', coalesce(p_payload->>'confidence', 'unknown'),
    p_payload->>'source_url', p_payload->>'evidence_snippet',
    coalesce((p_payload->>'is_primary')::boolean, false))
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;

-- ===========================================================================
-- Drafts: one thread per (facility, campaign); a draft is an append-only row
-- ===========================================================================
-- p_payload: { facility_id, contact_id, campaign_id, subject, body, body_sha256 }
-- provider is forced to 'mock': nothing written here can reach a real mailbox.
CREATE OR REPLACE FUNCTION public.swim_record_draft(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_facility UUID := (p_payload->>'facility_id')::uuid;
  v_campaign UUID := (p_payload->>'campaign_id')::uuid;
  v_sha      TEXT := p_payload->>'body_sha256';
  v_thread   UUID;
  v_message  UUID;
  v_new      BOOLEAN := false;
BEGIN
  IF v_facility IS NULL OR v_campaign IS NULL THEN
    RAISE EXCEPTION 'facility_id and campaign_id are required';
  END IF;
  IF coalesce(p_payload->>'body', '') = '' OR coalesce(v_sha, '') = '' THEN
    RAISE EXCEPTION 'body and body_sha256 are required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM swim_sourcing.facilities WHERE id = v_facility AND company_id = p_company_id) THEN
    RAISE EXCEPTION 'facility % not found for company %', v_facility, p_company_id;
  END IF;

  INSERT INTO swim_sourcing.outreach_threads (
    company_id, facility_id, contact_id, campaign_id, provider, subject, state)
  VALUES (
    p_company_id, v_facility, (p_payload->>'contact_id')::uuid, v_campaign, 'mock',
    p_payload->>'subject', 'draft')
  ON CONFLICT (facility_id, campaign_id) DO UPDATE
    SET subject = coalesce(EXCLUDED.subject, swim_sourcing.outreach_threads.subject),
        updated_at = now()
  RETURNING id INTO v_thread;

  -- Idempotent on exact bytes: the same draft asked twice is recorded once.
  SELECT id INTO v_message FROM swim_sourcing.outreach_messages
   WHERE thread_id = v_thread AND direction = 'outbound' AND body_sha256 = v_sha
   ORDER BY created_at DESC LIMIT 1;

  IF v_message IS NULL THEN
    INSERT INTO swim_sourcing.outreach_messages (
      company_id, thread_id, direction, body, subject, body_sha256, status)
    VALUES (
      p_company_id, v_thread, 'outbound', p_payload->>'body', p_payload->>'subject',
      v_sha, 'draft')
    RETURNING id INTO v_message;
    v_new := true;
  END IF;

  RETURN jsonb_build_object('thread_id', v_thread, 'message_id', v_message, 'was_new', v_new);
END $$;

-- ===========================================================================
-- Simulated inbound mail
-- ===========================================================================
-- p_payload: { thread_id, subject, body, scenario_id }
-- Subject MUST start with '[SIMULATED]' - the prototype has no real inbound
-- path, and this is the guard that keeps a scripted reply from ever being
-- mistaken for correspondence from a real facility.
CREATE OR REPLACE FUNCTION public.swim_record_inbound(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_thread  UUID := (p_payload->>'thread_id')::uuid;
  v_subject TEXT := p_payload->>'subject';
  v_body    TEXT := p_payload->>'body';
  v_id      UUID;
  v_facility UUID;
BEGIN
  IF v_thread IS NULL OR coalesce(v_body, '') = '' THEN
    RAISE EXCEPTION 'thread_id and body are required';
  END IF;
  IF v_subject IS NULL OR position('[SIMULATED]' in v_subject) <> 1 THEN
    RAISE EXCEPTION 'prototype inbound mail must carry a [SIMULATED] subject prefix';
  END IF;

  SELECT facility_id INTO v_facility FROM swim_sourcing.outreach_threads
   WHERE id = v_thread AND company_id = p_company_id;
  IF v_facility IS NULL THEN
    RAISE EXCEPTION 'thread % not found for company %', v_thread, p_company_id;
  END IF;

  INSERT INTO swim_sourcing.outreach_messages (
    company_id, thread_id, direction, body, subject, body_sha256, status, received_at)
  VALUES (
    p_company_id, v_thread, 'inbound', v_body, v_subject,
    encode(sha256(convert_to(regexp_replace(trim(v_body), E'\r\n', E'\n', 'g'), 'UTF8')), 'hex'),
    'received', now())
  RETURNING id INTO v_id;

  UPDATE swim_sourcing.outreach_threads
     SET state = 'replied', updated_at = now()
   WHERE id = v_thread;

  UPDATE swim_sourcing.facilities
     SET pipeline_stage = 'responded', updated_at = now()
   WHERE id = v_facility
     AND pipeline_stage IN ('discovered','qualified','needs_info','outreach_approved','contacted');

  RETURN v_id;
END $$;

-- ===========================================================================
-- Classification verdict for a thread
-- ===========================================================================
-- p_payload: { thread_id, intent, requires_approval, classification {...} }
-- The verdict is a PROPOSAL. Nothing here authorises a send.
CREATE OR REPLACE FUNCTION public.swim_record_classification(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_thread UUID := (p_payload->>'thread_id')::uuid;
  v_intent TEXT := p_payload->>'intent';
  v_approval BOOLEAN := coalesce((p_payload->>'requires_approval')::boolean, true);
  v_state TEXT;
  v_out JSONB;
BEGIN
  IF v_thread IS NULL OR coalesce(v_intent, '') = '' THEN
    RAISE EXCEPTION 'thread_id and intent are required';
  END IF;

  v_state := CASE
               WHEN v_intent = 'unsubscribe' THEN 'opted_out'
               WHEN v_approval THEN 'escalated'
               ELSE 'replied'
             END;

  UPDATE swim_sourcing.outreach_threads t
     SET last_intent = v_intent,
         state = v_state,
         last_classification = coalesce(p_payload->'classification', '{}'::jsonb)
                               || jsonb_build_object('recorded_at', now()),
         updated_at = now()
   WHERE t.id = v_thread AND t.company_id = p_company_id
   RETURNING jsonb_build_object('thread_id', t.id, 'state', t.state, 'last_intent', t.last_intent)
   INTO v_out;

  IF v_out IS NULL THEN
    RAISE EXCEPTION 'thread % not found for company %', v_thread, p_company_id;
  END IF;
  RETURN v_out;
END $$;

-- ===========================================================================
-- Dashboard reads
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.swim_list_research(
  p_company_id UUID,
  p_limit      INT DEFAULT 100
)
RETURNS TABLE (
  facility_id UUID, name TEXT, facility_type TEXT, source TEXT, website TEXT,
  distance_miles NUMERIC, pipeline_stage TEXT, triage_state TEXT, channel_recommended TEXT,
  qualification_status TEXT, completeness NUMERIC, known_count INT, unknown_count INT,
  contact_count INT, open_questions JSONB, updated_at TIMESTAMPTZ
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT f.id, f.name, f.facility_type, f.source, f.website, f.distance_miles,
         f.pipeline_stage,
         q.score_breakdown->>'triage_state',
         q.score_breakdown->>'channel_recommended',
         q.status, q.completeness,
         (SELECT count(*) FROM jsonb_object_keys(f.attributes))::int,
         coalesce(array_length(f.unknown_fields, 1), 0),
         (SELECT count(*) FROM swim_sourcing.facility_contacts c WHERE c.facility_id = f.id)::int,
         coalesce(q.open_questions, '[]'::jsonb),
         f.updated_at
  FROM swim_sourcing.facilities f
  LEFT JOIN LATERAL (
    SELECT status, completeness, score_breakdown, open_questions
    FROM swim_sourcing.qualifications WHERE facility_id = f.id
    ORDER BY created_at DESC LIMIT 1
  ) q ON true
  WHERE f.company_id = p_company_id
  ORDER BY CASE q.score_breakdown->>'triage_state'
             WHEN 'contact_first' THEN 0 WHEN 'research_further' THEN 1
             WHEN 'not_currently_suitable' THEN 2 WHEN 'disqualified' THEN 3 ELSE 4 END,
           f.distance_miles NULLS LAST, f.name
  LIMIT greatest(1, least(p_limit, 500));
$$;

CREATE OR REPLACE FUNCTION public.swim_list_drafts(
  p_company_id UUID,
  p_limit      INT DEFAULT 50
)
RETURNS TABLE (
  message_id UUID, thread_id UUID, facility_id UUID, facility_name TEXT,
  contact_name TEXT, contact_email TEXT, subject TEXT, body TEXT, status TEXT,
  thread_state TEXT, created_at TIMESTAMPTZ
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT DISTINCT ON (t.id)
         m.id, t.id, f.id, f.name, c.full_name, c.email, m.subject, m.body, m.status,
         t.state, m.created_at
  FROM swim_sourcing.outreach_threads t
  JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  JOIN swim_sourcing.outreach_messages m ON m.thread_id = t.id AND m.direction = 'outbound'
  LEFT JOIN swim_sourcing.facility_contacts c ON c.id = t.contact_id
  WHERE t.company_id = p_company_id
  ORDER BY t.id, m.created_at DESC
  LIMIT greatest(1, least(p_limit, 500));
$$;

CREATE OR REPLACE FUNCTION public.swim_list_threads(
  p_company_id UUID,
  p_limit      INT DEFAULT 50
)
RETURNS TABLE (
  thread_id UUID, facility_id UUID, facility_name TEXT, state TEXT, last_intent TEXT,
  subject TEXT, last_inbound_excerpt TEXT, last_inbound_at TIMESTAMPTZ,
  last_classification JSONB, outbound_count INT, inbound_count INT, updated_at TIMESTAMPTZ
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT t.id, f.id, f.name, t.state, t.last_intent, t.subject,
         (SELECT left(m.body, 280) FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'inbound'
           ORDER BY m.created_at DESC LIMIT 1),
         (SELECT max(m.received_at) FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'inbound'),
         t.last_classification,
         (SELECT count(*) FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'outbound')::int,
         (SELECT count(*) FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'inbound')::int,
         t.updated_at
  FROM swim_sourcing.outreach_threads t
  JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  WHERE t.company_id = p_company_id
  ORDER BY t.updated_at DESC
  LIMIT greatest(1, least(p_limit, 500));
$$;

-- Derived, never stored: what a human or the controller should do next.
CREATE OR REPLACE FUNCTION public.swim_next_actions(p_company_id UUID)
RETURNS TABLE (
  action_type TEXT, priority INT, facility_id UUID, facility_name TEXT,
  thread_id UUID, detail TEXT
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  -- 1. Escalated replies: Cameron decides.
  SELECT 'review_escalation', 1, f.id, f.name, t.id,
         coalesce(t.last_classification->>'summary', 'reply touches a topic that requires a decision')
  FROM swim_sourcing.outreach_threads t JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  WHERE t.company_id = p_company_id AND t.state = 'escalated'
  UNION ALL
  -- 2. Opt-outs: must be suppressed (write path is MVP 2; surfaced here).
  SELECT 'suppress_contact', 1, f.id, f.name, t.id, 'contact asked not to be contacted again'
  FROM swim_sourcing.outreach_threads t JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  WHERE t.company_id = p_company_id AND t.state = 'opted_out'
  UNION ALL
  -- 3. Replied, not escalated: a reply is proposed and awaits review.
  SELECT 'review_proposed_reply', 2, f.id, f.name, t.id,
         coalesce(t.last_classification->>'proposed_action', 'proposed reply awaits review')
  FROM swim_sourcing.outreach_threads t JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  WHERE t.company_id = p_company_id AND t.state = 'replied' AND t.last_classification IS NOT NULL
  UNION ALL
  -- 4. Drafts awaiting review.
  SELECT 'review_draft', 3, f.id, f.name, t.id, 'draft prepared; nothing is sent in the prototype'
  FROM swim_sourcing.outreach_threads t JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  WHERE t.company_id = p_company_id AND t.state = 'draft'
  UNION ALL
  -- 5. Contactable facilities with no thread yet.
  SELECT 'prepare_outreach', 3, f.id, f.name, NULL::uuid, 'contact route evidenced; no draft yet'
  FROM swim_sourcing.facilities f
  JOIN LATERAL (SELECT score_breakdown FROM swim_sourcing.qualifications
                WHERE facility_id = f.id ORDER BY created_at DESC LIMIT 1) q ON true
  WHERE f.company_id = p_company_id
    AND q.score_breakdown->>'triage_state' = 'contact_first'
    AND NOT EXISTS (SELECT 1 FROM swim_sourcing.outreach_threads t WHERE t.facility_id = f.id)
  UNION ALL
  -- 6. Research further.
  SELECT 'research_further', 4, f.id, f.name, NULL::uuid, 'no evidenced contact route yet'
  FROM swim_sourcing.facilities f
  JOIN LATERAL (SELECT score_breakdown FROM swim_sourcing.qualifications
                WHERE facility_id = f.id ORDER BY created_at DESC LIMIT 1) q ON true
  WHERE f.company_id = p_company_id
    AND q.score_breakdown->>'triage_state' = 'research_further'
  ORDER BY 2, 4;
$$;

-- Objective progress with explicit denominators. All counts, no opinions.
CREATE OR REPLACE FUNCTION public.swim_objective_progress(p_company_id UUID)
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  WITH latest_q AS (
    SELECT DISTINCT ON (facility_id) facility_id, score_breakdown, open_questions
    FROM swim_sourcing.qualifications
    WHERE company_id = p_company_id
    ORDER BY facility_id, created_at DESC
  )
  SELECT jsonb_build_object(
    'target_partnerships', 1,
    'secured',             (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id AND pipeline_stage = 'secured'),
    'facilities_total',    (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id),
    'facilities_fixture',  (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id AND source = 'fixture'),
    'facilities_live',     (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id AND source = 'google_places'),
    'enriched',            (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id AND attributes <> '{}'::jsonb),
    'with_contact',        (SELECT count(DISTINCT c.facility_id) FROM swim_sourcing.facility_contacts c WHERE c.company_id = p_company_id),
    'triaged',             (SELECT count(*) FROM latest_q),
    'contact_first',       (SELECT count(*) FROM latest_q WHERE score_breakdown->>'triage_state' = 'contact_first'),
    'research_further',    (SELECT count(*) FROM latest_q WHERE score_breakdown->>'triage_state' = 'research_further'),
    'not_currently_suitable', (SELECT count(*) FROM latest_q WHERE score_breakdown->>'triage_state' = 'not_currently_suitable'),
    'disqualified',        (SELECT count(*) FROM latest_q WHERE score_breakdown->>'triage_state' = 'disqualified'),
    'open_questions_total',(SELECT coalesce(sum(jsonb_array_length(coalesce(open_questions, '[]'::jsonb))), 0) FROM latest_q),
    'threads',             (SELECT count(*) FROM swim_sourcing.outreach_threads WHERE company_id = p_company_id),
    'drafts',              (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND direction = 'outbound' AND status = 'draft'),
    'sent',                (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND status = 'sent'),
    'replies',             (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND direction = 'inbound'),
    'classified',          (SELECT count(*) FROM swim_sourcing.outreach_threads WHERE company_id = p_company_id AND last_classification IS NOT NULL),
    'escalated',           (SELECT count(*) FROM swim_sourcing.outreach_threads WHERE company_id = p_company_id AND state = 'escalated'),
    'opted_out',           (SELECT count(*) FROM swim_sourcing.outreach_threads WHERE company_id = p_company_id AND state = 'opted_out'),
    'jobs', (SELECT coalesce(jsonb_object_agg(status, n), '{}'::jsonb) FROM (
               SELECT status, count(*) AS n FROM swim_sourcing.jobs WHERE company_id = p_company_id GROUP BY status) j),
    'generated_at', now());
$$;

-- ===========================================================================
-- service_role only, for every swim_* function (re-applied so the new ones
-- are covered; harmless for the ones 050 already restricted).
-- ===========================================================================
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.proname AS fn, pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'swim\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC, anon, authenticated', r.fn, r.args);
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.%I(%s) TO service_role', r.fn, r.args);
  END LOOP;
END $$;

COMMIT;
