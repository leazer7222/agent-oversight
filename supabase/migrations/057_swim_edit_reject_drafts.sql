-- Migration 057: edit and reject drafts
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 049, 053, 055, 056
-- Status: AUTHORED 2026-11-08.
--
-- Until now the only decision a person could record on a draft was "approve".
-- This adds the other two:
--   * EDIT: public.swim_update_draft rewrites the subject/body of an unsent
--     outbound message. The previous text is kept in swim_sourcing.message_revisions
--     (append-only), the message drops back to 'draft' and any approval is void
--     (the send chokepoint compares the approval hash to the body at send time,
--     so this is belt and braces). The unsubscribe line must survive the edit.
--   * REJECT: swim_record_approval with decision 'rejected' now parks the message
--     in status 'rejected' (new value) instead of returning it to 'draft', so it
--     stops showing as "needs approval". The next "Write or rewrite drafts" run
--     replaces it; "do not contact" is a separate suppression (existing RPC).
-- swim_list_thread_campaigns stops listing threads whose contact is suppressed,
-- so a redraft never writes to a do-not-contact address.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. New status / state values (closed CHECK enums: recreate with every value)
-- ---------------------------------------------------------------------------
ALTER TABLE swim_sourcing.outreach_messages DROP CONSTRAINT IF EXISTS outreach_messages_status_check;
ALTER TABLE swim_sourcing.outreach_messages ADD CONSTRAINT outreach_messages_status_check
  CHECK (status IN ('draft', 'approved', 'sending', 'sent', 'failed', 'received', 'rejected'));

ALTER TABLE swim_sourcing.outreach_threads DROP CONSTRAINT IF EXISTS outreach_threads_state_check;
ALTER TABLE swim_sourcing.outreach_threads ADD CONSTRAINT outreach_threads_state_check
  CHECK (state IN ('draft', 'approved', 'sent', 'awaiting_reply', 'replied', 'escalated',
                   'closed_won', 'closed_lost', 'opted_out', 'rejected'));

-- ---------------------------------------------------------------------------
-- 2. Revision history for edited drafts (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS swim_sourcing.message_revisions (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id       UUID        NOT NULL,
  message_id       UUID        NOT NULL,
  previous_subject TEXT,
  previous_body    TEXT        NOT NULL,
  previous_sha256  TEXT,
  previous_status  TEXT,
  edited_by        UUID,
  editor_label     TEXT,
  note             TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.message_revisions
  ADD CONSTRAINT fk_message_revisions_message
  FOREIGN KEY (message_id) REFERENCES swim_sourcing.outreach_messages(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS ix_message_revisions_message
  ON swim_sourcing.message_revisions (message_id, created_at);

ALTER TABLE swim_sourcing.message_revisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all ON swim_sourcing.message_revisions;
CREATE POLICY service_role_all ON swim_sourcing.message_revisions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
-- A revision is a ledger entry: never updated, never deleted (public.forbid_mutation, 048).
DROP TRIGGER IF EXISTS trg_message_revisions_immutable ON swim_sourcing.message_revisions;
CREATE TRIGGER trg_message_revisions_immutable
  BEFORE UPDATE OR DELETE ON swim_sourcing.message_revisions
  FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation();

COMMENT ON TABLE swim_sourcing.message_revisions IS
  'Previous text of an outbound draft each time a person edited it. Append-only.';

-- ---------------------------------------------------------------------------
-- 3. Edit a draft
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.swim_update_draft(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE
  v_id      UUID := (p_payload->>'message_id')::uuid;
  v_subject TEXT := nullif(trim(p_payload->>'subject'), '');
  v_body    TEXT := p_payload->>'body';
  v_user    UUID := (p_payload->>'editor_user_id')::uuid;
  v_label   TEXT := coalesce(p_payload->>'editor_label', (p_payload->>'editor_user_id'));
  v_note    TEXT := p_payload->>'note';
  m         swim_sourcing.outreach_messages%ROWTYPE;
  v_sha     TEXT;
  v_rev     UUID;
BEGIN
  IF v_id IS NULL OR v_user IS NULL THEN
    RAISE EXCEPTION 'message_id and editor_user_id are required';
  END IF;
  IF v_body IS NULL OR length(trim(v_body)) < 40 THEN
    RAISE EXCEPTION 'the email body is too short to send';
  END IF;
  IF v_body !~* 'unsubscribe' THEN
    RAISE EXCEPTION 'the email must keep the unsubscribe line (commercial email rule)';
  END IF;

  SELECT * INTO m FROM swim_sourcing.outreach_messages
   WHERE id = v_id AND company_id = p_company_id AND direction = 'outbound'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'message % not found for company %', v_id, p_company_id;
  END IF;
  IF m.status NOT IN ('draft', 'approved', 'failed', 'rejected') THEN
    RAISE EXCEPTION 'a message with status % cannot be edited', m.status;
  END IF;

  IF trim(m.body) = trim(v_body) AND coalesce(v_subject, m.subject) IS NOT DISTINCT FROM m.subject THEN
    RETURN jsonb_build_object('message_id', v_id, 'status', m.status, 'changed', false);
  END IF;

  INSERT INTO swim_sourcing.message_revisions (
    company_id, message_id, previous_subject, previous_body, previous_sha256, previous_status,
    edited_by, editor_label, note)
  VALUES (p_company_id, v_id, m.subject, m.body, m.body_sha256, m.status, v_user, v_label, v_note)
  RETURNING id INTO v_rev;

  v_sha := encode(sha256(convert_to(regexp_replace(trim(v_body), E'\r\n', E'\n', 'g'), 'UTF8')), 'hex');

  UPDATE swim_sourcing.outreach_messages
     SET subject = coalesce(v_subject, subject),
         body = v_body,
         body_sha256 = v_sha,
         status = 'draft',
         approved_by = NULL,
         approved_at = NULL,
         error = NULL
   WHERE id = v_id;

  UPDATE swim_sourcing.outreach_threads
     SET state = 'draft', subject = coalesce(v_subject, subject), updated_at = now()
   WHERE id = m.thread_id AND state IN ('draft', 'approved', 'rejected');

  RETURN jsonb_build_object('message_id', v_id, 'status', 'draft', 'changed', true,
                            'body_sha256', v_sha, 'revision_id', v_rev);
END $$;

REVOKE ALL ON FUNCTION public.swim_update_draft(UUID, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.swim_update_draft(UUID, JSONB) TO service_role;

-- ---------------------------------------------------------------------------
-- 4. Reject parks the message instead of returning it to the approval queue
-- ---------------------------------------------------------------------------
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
       SET status = CASE WHEN v_decision = 'approved' THEN 'approved' ELSE 'rejected' END,
           approved_by = CASE WHEN v_decision = 'approved' THEN v_user ELSE NULL END,
           approved_at = CASE WHEN v_decision = 'approved' THEN now() ELSE NULL END
     WHERE id = v_subject AND status IN ('draft', 'approved', 'failed', 'rejected');
    UPDATE swim_sourcing.outreach_threads t
       SET state = CASE WHEN v_decision = 'approved' THEN 'approved' ELSE 'rejected' END,
           updated_at = now()
      FROM swim_sourcing.outreach_messages m
     WHERE m.id = v_subject AND t.id = m.thread_id AND t.state IN ('draft', 'approved', 'rejected');
  END IF;

  RETURN jsonb_build_object('approval_id', v_id, 'approved_sha256', v_sha, 'decision', v_decision);
END $$;

-- ---------------------------------------------------------------------------
-- 5. Redraft candidates never include a do-not-contact address
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.swim_list_thread_campaigns(
  p_company_id UUID
)
RETURNS TABLE (
  thread_id UUID, facility_id UUID, facility_name TEXT, campaign_id UUID, state TEXT,
  inbound_count INT, latest_outbound_status TEXT
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT t.id, f.id, f.name, t.campaign_id, t.state,
         (SELECT count(*)::int FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'inbound'),
         (SELECT m.status FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'outbound'
           ORDER BY m.created_at DESC LIMIT 1)
  FROM swim_sourcing.outreach_threads t
  JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  LEFT JOIN swim_sourcing.facility_contacts c ON c.id = t.contact_id
  WHERE t.company_id = p_company_id
    AND t.state <> 'opted_out'
    AND NOT EXISTS (SELECT 1 FROM swim_sourcing.suppression_list s
                     WHERE s.company_id = p_company_id AND c.email IS NOT NULL
                       AND lower(s.email) = lower(c.email))
  ORDER BY t.updated_at DESC;
$$;

-- ---------------------------------------------------------------------------
-- 6. Pending jobs of a type (the worker's automatic inbox check uses it so a
--    slow tick never piles up duplicate mailbox polls)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.swim_list_pending_jobs(
  p_company_id UUID,
  p_job_type   TEXT
)
RETURNS TABLE (job_id UUID, status TEXT, created_at TIMESTAMPTZ)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT j.id, j.status, j.created_at
  FROM swim_sourcing.jobs j
  WHERE j.company_id = p_company_id AND j.job_type = p_job_type
    AND j.status IN ('queued', 'running')
  ORDER BY j.created_at;
$$;

REVOKE ALL ON FUNCTION public.swim_list_pending_jobs(UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.swim_list_pending_jobs(UUID, TEXT) TO service_role;

COMMIT;
