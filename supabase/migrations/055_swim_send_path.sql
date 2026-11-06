-- Migration 055: the send path - approval, chokepoint, durable send state, real inbound
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 049, 050, 053
-- Status: AUTHORED 2026-11-06 for MVP 2 step 1 (supervised test sending).
--
-- Every function here is service_role only and lives in `public` because
-- PostgREST does not expose swim_sourcing. No new tables, no constraint
-- changes. The campaigns entity from the final design (section E.1) is NOT in
-- this migration: the first real sends are a supervised test to an operator
-- allow-list enforced by the worker, and campaign scope/caps follow once that
-- path is proven. Nothing here relaxes the rule that a send requires an
-- approval row whose hash equals the exact bytes being sent.

BEGIN;

-- ===========================================================================
-- Approval: bind an authenticated identity to the exact bytes of a message
-- ===========================================================================
-- p_payload: { subject_type, subject_id, decision, approver_user_id, approver_label, note }
-- For subject_type='message' the current body is hashed server-side so the
-- approval binds bytes the approver actually saw; an edit afterwards voids it.
CREATE OR REPLACE FUNCTION public.swim_record_approval(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_type     TEXT := p_payload->>'subject_type';
  v_subject  UUID := (p_payload->>'subject_id')::uuid;
  v_decision TEXT := p_payload->>'decision';
  v_user     UUID := (p_payload->>'approver_user_id')::uuid;
  v_sha      TEXT;
  v_id       UUID;
BEGIN
  IF v_type IS NULL OR v_subject IS NULL OR v_decision NOT IN ('approved','rejected') OR v_user IS NULL THEN
    RAISE EXCEPTION 'subject_type, subject_id, decision (approved|rejected) and approver_user_id are required';
  END IF;

  IF v_type = 'message' THEN
    SELECT encode(sha256(convert_to(regexp_replace(trim(m.body), E'\r\n', E'\n', 'g'), 'UTF8')), 'hex')
      INTO v_sha
      FROM swim_sourcing.outreach_messages m
     WHERE m.id = v_subject AND m.company_id = p_company_id AND m.direction = 'outbound';
    IF v_sha IS NULL THEN
      RAISE EXCEPTION 'message % not found for company %', v_subject, p_company_id;
    END IF;
  END IF;

  INSERT INTO swim_sourcing.approvals (
    company_id, subject_type, subject_id, decision, approved_sha256,
    approver_user_id, approver_label, note)
  VALUES (
    p_company_id, v_type, v_subject, v_decision, v_sha, v_user,
    coalesce(p_payload->>'approver_label', v_user::text), p_payload->>'note')
  RETURNING id INTO v_id;

  IF v_type = 'message' THEN
    UPDATE swim_sourcing.outreach_messages
       SET status = CASE WHEN v_decision = 'approved' THEN 'approved' ELSE 'draft' END,
           approved_by = CASE WHEN v_decision = 'approved' THEN v_user ELSE NULL END,
           approved_at = CASE WHEN v_decision = 'approved' THEN now() ELSE NULL END
     WHERE id = v_subject AND status IN ('draft','approved');
    UPDATE swim_sourcing.outreach_threads t
       SET state = CASE WHEN v_decision = 'approved' THEN 'approved' ELSE 'draft' END,
           updated_at = now()
      FROM swim_sourcing.outreach_messages m
     WHERE m.id = v_subject AND t.id = m.thread_id AND t.state IN ('draft','approved');
  END IF;

  RETURN jsonb_build_object('approval_id', v_id, 'approved_sha256', v_sha, 'decision', v_decision);
END $$;

-- ===========================================================================
-- The chokepoint: may THIS message go to THIS recipient right now?
-- ===========================================================================
-- Returns { allowed, reasons[], thread_id, subject, body, body_sha256,
--           approval_id, sent_today, daily_cap }. Deny reasons are explicit and
--           all evaluated, so an operator sees everything that blocks a send.
CREATE OR REPLACE FUNCTION public.swim_authorize_send(
  p_company_id UUID,
  p_message_id UUID,
  p_recipient  TEXT,
  p_daily_cap  INT DEFAULT 8
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
STABLE
AS $$
DECLARE
  m        swim_sourcing.outreach_messages%ROWTYPE;
  v_sha    TEXT;
  v_appr   swim_sourcing.approvals%ROWTYPE;
  v_sent_today INT;
  v_prior  INT;
  v_reasons TEXT[] := ARRAY[]::TEXT[];
BEGIN
  SELECT * INTO m FROM swim_sourcing.outreach_messages
   WHERE id = p_message_id AND company_id = p_company_id;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('allowed', false, 'reasons', jsonb_build_array('message not found'));
  END IF;
  IF m.direction <> 'outbound' THEN
    v_reasons := v_reasons || 'not an outbound message';
  END IF;
  IF m.status = 'sent' THEN
    v_reasons := v_reasons || 'already sent';
  ELSIF m.status = 'sending' THEN
    v_reasons := v_reasons || 'a previous attempt is unresolved - reconcile first';
  ELSIF m.status <> 'approved' THEN
    v_reasons := v_reasons || format('status is %s, not approved', m.status);
  END IF;

  v_sha := encode(sha256(convert_to(regexp_replace(trim(m.body), E'\r\n', E'\n', 'g'), 'UTF8')), 'hex');
  SELECT * INTO v_appr FROM swim_sourcing.approvals
   WHERE company_id = p_company_id AND subject_type = 'message' AND subject_id = p_message_id
   ORDER BY created_at DESC LIMIT 1;
  IF NOT FOUND THEN
    v_reasons := v_reasons || 'no approval recorded by an authenticated user';
  ELSIF v_appr.decision <> 'approved' THEN
    v_reasons := v_reasons || 'latest decision is rejected';
  ELSIF v_appr.approved_sha256 IS DISTINCT FROM v_sha THEN
    v_reasons := v_reasons || 'message body changed after approval - the approval is void';
  END IF;

  IF p_recipient IS NULL OR p_recipient = '' THEN
    v_reasons := v_reasons || 'no recipient';
  ELSIF EXISTS (SELECT 1 FROM swim_sourcing.suppression_list s
                 WHERE s.company_id = p_company_id AND lower(s.email) = lower(p_recipient)) THEN
    v_reasons := v_reasons || 'recipient is on the do-not-contact list';
  END IF;

  SELECT count(*) INTO v_prior FROM swim_sourcing.outreach_messages o
   WHERE o.thread_id = m.thread_id AND o.direction = 'outbound' AND o.status = 'sent' AND o.id <> m.id;
  -- Prototype rule: one sent message per thread. Follow-ups arrive with campaigns.
  IF v_prior > 0 THEN
    v_reasons := v_reasons || 'this thread already has a sent message (follow-ups are not enabled yet)';
  END IF;

  SELECT count(*) INTO v_sent_today FROM swim_sourcing.outreach_messages o
   WHERE o.company_id = p_company_id AND o.direction = 'outbound' AND o.status = 'sent'
     AND o.sent_at >= date_trunc('day', now() AT TIME ZONE 'America/Chicago') AT TIME ZONE 'America/Chicago';
  IF v_sent_today >= coalesce(p_daily_cap, 8) THEN
    v_reasons := v_reasons || format('daily cap reached (%s of %s today)', v_sent_today, p_daily_cap);
  END IF;

  RETURN jsonb_build_object(
    'allowed', coalesce(array_length(v_reasons, 1), 0) = 0,
    'reasons', to_jsonb(v_reasons),
    'thread_id', m.thread_id,
    'subject', m.subject,
    'body', m.body,
    'body_sha256', v_sha,
    'approval_id', v_appr.id,
    'sent_today', v_sent_today,
    'daily_cap', p_daily_cap);
END $$;

-- ===========================================================================
-- Durable send state (the protocol in outreach-agent/send.py, persisted)
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.swim_mark_sending(
  p_company_id UUID, p_message_id UUID, p_attempt_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE n INT;
BEGIN
  UPDATE swim_sourcing.outreach_messages
     SET status = 'sending', send_attempt_id = p_attempt_id, error = NULL
   WHERE id = p_message_id AND company_id = p_company_id AND status = 'approved';
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;

CREATE OR REPLACE FUNCTION public.swim_mark_sent(
  p_company_id UUID, p_message_id UUID, p_provider_message_id TEXT, p_provider_thread_id TEXT
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_thread UUID; v_facility UUID;
BEGIN
  UPDATE swim_sourcing.outreach_messages
     SET status = 'sent', provider_message_id = p_provider_message_id,
         provider_thread_id = p_provider_thread_id, sent_at = now(), error = NULL
   WHERE id = p_message_id AND company_id = p_company_id AND status IN ('sending','approved')
   RETURNING thread_id INTO v_thread;
  IF v_thread IS NULL THEN
    RAISE EXCEPTION 'message % is not in a sendable state', p_message_id;
  END IF;
  UPDATE swim_sourcing.outreach_threads
     SET state = 'awaiting_reply', provider = 'gmail',
         provider_thread_id = coalesce(provider_thread_id, p_provider_thread_id),
         updated_at = now()
   WHERE id = v_thread
   RETURNING facility_id INTO v_facility;
  UPDATE swim_sourcing.facilities
     SET pipeline_stage = 'contacted', updated_at = now()
   WHERE id = v_facility AND pipeline_stage IN ('discovered','qualified','needs_info','outreach_approved');
  RETURN jsonb_build_object('message_id', p_message_id, 'thread_id', v_thread, 'facility_id', v_facility);
END $$;

-- Hard failure or reconciled-as-not-delivered: back to 'approved' so the SAME
-- approved bytes can be retried; the approval still binds them.
CREATE OR REPLACE FUNCTION public.swim_mark_send_failed(
  p_company_id UUID, p_message_id UUID, p_error TEXT, p_retryable BOOLEAN DEFAULT true
)
RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE n INT;
BEGIN
  UPDATE swim_sourcing.outreach_messages
     SET status = CASE WHEN p_retryable THEN 'approved' ELSE 'failed' END,
         send_attempt_id = CASE WHEN p_retryable THEN NULL ELSE send_attempt_id END,
         error = left(p_error, 500)
   WHERE id = p_message_id AND company_id = p_company_id AND status IN ('sending','approved');
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;

-- Messages the send/reconcile jobs should look at, with the intended recipient.
CREATE OR REPLACE FUNCTION public.swim_list_send_candidates(p_company_id UUID)
RETURNS TABLE (
  message_id UUID, thread_id UUID, facility_id UUID, facility_name TEXT,
  status TEXT, send_attempt_id UUID, intended_recipient TEXT, subject TEXT, approved_at TIMESTAMPTZ
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT m.id, t.id, f.id, f.name, m.status, m.send_attempt_id, c.email, m.subject, m.approved_at
  FROM swim_sourcing.outreach_messages m
  JOIN swim_sourcing.outreach_threads t ON t.id = m.thread_id
  JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  LEFT JOIN swim_sourcing.facility_contacts c ON c.id = t.contact_id
  WHERE m.company_id = p_company_id AND m.direction = 'outbound'
    AND m.status IN ('approved','sending')
  ORDER BY m.approved_at NULLS LAST, m.created_at;
$$;

-- ===========================================================================
-- Suppression write path
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.swim_add_suppression(
  p_company_id UUID, p_email TEXT, p_reason TEXT, p_note TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_id UUID;
BEGIN
  IF coalesce(trim(p_email), '') = '' THEN
    RAISE EXCEPTION 'email is required';
  END IF;
  SELECT id INTO v_id FROM swim_sourcing.suppression_list
   WHERE company_id = p_company_id AND lower(email) = lower(trim(p_email));
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  INSERT INTO swim_sourcing.suppression_list (company_id, email, reason, note)
  VALUES (p_company_id, trim(p_email), p_reason, p_note)
  RETURNING id INTO v_id;
  UPDATE swim_sourcing.outreach_threads t
     SET state = 'opted_out', updated_at = now()
    FROM swim_sourcing.facility_contacts c
   WHERE t.contact_id = c.id AND t.company_id = p_company_id
     AND lower(c.email) = lower(trim(p_email)) AND t.state <> 'opted_out';
  RETURN v_id;
END $$;

-- ===========================================================================
-- Real inbound mail (from the mailbox), matched to our thread by In-Reply-To
-- ===========================================================================
-- p_payload: { provider_message_id, in_reply_to, references[], from_email,
--              subject, body, received_at }
-- Returns { message_id, thread_id, matched } ; matched=false means no thread of
-- ours was referenced and nothing was written (we do not ingest unrelated mail).
CREATE OR REPLACE FUNCTION public.swim_record_inbound_real(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_pmid   TEXT := nullif(trim(p_payload->>'provider_message_id'), '');
  v_refs   TEXT[] := ARRAY(SELECT jsonb_array_elements_text(coalesce(p_payload->'references', '[]'::jsonb)))
                     || ARRAY[coalesce(p_payload->>'in_reply_to', '')];
  v_thread UUID;
  v_facility UUID;
  v_id     UUID;
  v_body   TEXT := p_payload->>'body';
BEGIN
  IF v_pmid IS NULL OR coalesce(v_body, '') = '' THEN
    RAISE EXCEPTION 'provider_message_id and body are required';
  END IF;
  -- Idempotent on the provider id.
  SELECT id, thread_id INTO v_id, v_thread FROM swim_sourcing.outreach_messages
   WHERE provider_message_id = v_pmid;
  IF v_id IS NOT NULL THEN
    RETURN jsonb_build_object('message_id', v_id, 'thread_id', v_thread, 'matched', true, 'duplicate', true);
  END IF;

  SELECT o.thread_id INTO v_thread FROM swim_sourcing.outreach_messages o
   WHERE o.company_id = p_company_id AND o.direction = 'outbound'
     AND o.provider_message_id = ANY (SELECT nullif(trim(x), '') FROM unnest(v_refs) x)
   ORDER BY o.created_at DESC LIMIT 1;
  IF v_thread IS NULL THEN
    RETURN jsonb_build_object('message_id', NULL, 'thread_id', NULL, 'matched', false);
  END IF;

  INSERT INTO swim_sourcing.outreach_messages (
    company_id, thread_id, direction, body, subject, body_sha256, status,
    provider_message_id, received_at)
  VALUES (
    p_company_id, v_thread, 'inbound', v_body, p_payload->>'subject',
    encode(sha256(convert_to(regexp_replace(trim(v_body), E'\r\n', E'\n', 'g'), 'UTF8')), 'hex'),
    'received', v_pmid,
    coalesce((p_payload->>'received_at')::timestamptz, now()))
  RETURNING id INTO v_id;

  UPDATE swim_sourcing.outreach_threads
     SET state = 'replied', updated_at = now()
   WHERE id = v_thread
   RETURNING facility_id INTO v_facility;
  UPDATE swim_sourcing.facilities
     SET pipeline_stage = 'responded', updated_at = now()
   WHERE id = v_facility
     AND pipeline_stage IN ('discovered','qualified','needs_info','outreach_approved','contacted');

  RETURN jsonb_build_object('message_id', v_id, 'thread_id', v_thread, 'matched', true, 'duplicate', false);
END $$;

-- Outbound provider ids known to us, for the inbound matcher and reconciliation.
CREATE OR REPLACE FUNCTION public.swim_list_outbound_provider_ids(p_company_id UUID, p_limit INT DEFAULT 500)
RETURNS TABLE (message_id UUID, thread_id UUID, provider_message_id TEXT, sent_at TIMESTAMPTZ)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT id, thread_id, provider_message_id, sent_at
  FROM swim_sourcing.outreach_messages
  WHERE company_id = p_company_id AND direction = 'outbound' AND provider_message_id IS NOT NULL
  ORDER BY sent_at DESC NULLS LAST
  LIMIT greatest(1, least(p_limit, 2000));
$$;

-- service_role only
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.proname AS fn, pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname IN (
      'swim_record_approval','swim_authorize_send','swim_mark_sending','swim_mark_sent',
      'swim_mark_send_failed','swim_list_send_candidates','swim_add_suppression',
      'swim_record_inbound_real','swim_list_outbound_provider_ids')
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC, anon, authenticated', r.fn, r.args);
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.%I(%s) TO service_role', r.fn, r.args);
  END LOOP;
END $$;

COMMIT;
