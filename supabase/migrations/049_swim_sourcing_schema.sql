-- Migration 049: swim_sourcing domain schema + durable job queue
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 001 (companies), 047 (hardening), 048 (company_members, credentials)
-- Status: AUTHORED, NOT APPLIED.
--
-- ARCHITECTURE: shared capabilities, separate business data.
--   The control plane (public/platform) keeps company + agent registry, runs,
--   events, cost, credentials, approvals-identity. This schema holds ONLY
--   Cameron's domain rows. The agents that read and write it are tenant-agnostic
--   and take (company_id, schema) as configuration, so a second business gets a
--   second schema with these same shapes and reuses the same agent code. Nothing
--   in this file is swim-specific except the table names and a few columns; the
--   pipeline shape is deliberately generic prospect-sourcing.
--
--   swim_sourcing is also the EXTRACTION SEAM: if this outgrows the control
--   plane it lifts out as a unit without touching public/platform.
--
-- Every table carries company_id even though this schema currently serves one
-- company. That is not redundancy - it is what lets a query be tenant-filtered
-- identically here and in any future shared-schema arrangement, and it is what
-- the RLS policies bind to.

BEGIN;

CREATE SCHEMA IF NOT EXISTS swim_sourcing;

-- Close the default-privilege hole for this brand-new schema. Migration 047's
-- global guard (ALTER DEFAULT PRIVILEGES FOR ROLE postgres) already covers it,
-- but being explicit here means this migration is correct even if applied to a
-- database where 047 has not run.
ALTER DEFAULT PRIVILEGES IN SCHEMA swim_sourcing
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA swim_sourcing
  REVOKE ALL ON TABLES FROM anon, authenticated;
REVOKE ALL ON SCHEMA swim_sourcing FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA swim_sourcing TO service_role;

-- ===========================================================================
-- Facilities: the prospect record
-- ===========================================================================
-- Provenance is mandatory, not optional. source + source_url + fetched_at exist
-- so that "where did this come from?" is always answerable, and so a reviewer
-- can tell a Places API result from an LLM inference. attributes_confidence
-- records per-field confidence; unknown_fields names what we explicitly do not
-- know, so absence of data is representable rather than implied.
CREATE TABLE swim_sourcing.facilities (
  id                 UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id         UUID        NOT NULL,
  name               TEXT        NOT NULL,
  facility_type      TEXT        NOT NULL DEFAULT 'unknown'
                       CHECK (facility_type IN ('hotel','gym','aquatic_center','recreation_center',
                                                'hoa_community','school','private_club','swim_school',
                                                'other','unknown')),
  address            TEXT,
  city               TEXT,
  state              TEXT,
  postal_code        TEXT,
  latitude           DOUBLE PRECISION,
  longitude          DOUBLE PRECISION,
  distance_miles     NUMERIC,
  phone              TEXT,
  website            TEXT,
  -- Provenance (mandatory)
  source             TEXT        NOT NULL
                       CHECK (source IN ('google_places','manual','website_crawl','fixture')),
  source_ref         TEXT,                      -- e.g. Places place_id; stable external id
  source_url         TEXT,
  source_fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Epistemics
  attributes         JSONB       NOT NULL DEFAULT '{}'::jsonb,
  attributes_confidence JSONB    NOT NULL DEFAULT '{}'::jsonb,
  unknown_fields     TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
  -- Pipeline
  pipeline_stage     TEXT        NOT NULL DEFAULT 'discovered'
                       CHECK (pipeline_stage IN ('discovered','qualified','disqualified','needs_info',
                                                 'outreach_approved','contacted','responded',
                                                 'meeting_scheduled','negotiating','secured','rejected')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

ALTER TABLE swim_sourcing.facilities
  ADD CONSTRAINT fk_facilities_company
  FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;

-- Deduplication. source_ref (Places place_id) is the strong key; the name+address
-- index catches the same facility arriving from a different source.
CREATE UNIQUE INDEX ux_facilities_company_source_ref
  ON swim_sourcing.facilities (company_id, source_ref)
  WHERE source_ref IS NOT NULL;
CREATE UNIQUE INDEX ux_facilities_company_name_addr
  ON swim_sourcing.facilities (company_id, lower(name), lower(coalesce(address, '')));
CREATE INDEX ix_facilities_stage ON swim_sourcing.facilities (company_id, pipeline_stage);

-- ===========================================================================
-- Contacts: decision-makers, with evidence
-- ===========================================================================
-- evidence_snippet must be text actually present on the page at source_url.
-- A contact with no on-page evidence is rejected by the agent rather than
-- stored with low confidence - a guessed email address is worse than no
-- address, because someone will eventually send mail to it.
CREATE TABLE swim_sourcing.facility_contacts (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id       UUID        NOT NULL,
  facility_id      UUID        NOT NULL,
  full_name        TEXT,
  role_title       TEXT,
  email            TEXT,
  phone            TEXT,
  confidence       TEXT        NOT NULL DEFAULT 'unknown'
                     CHECK (confidence IN ('verified','inferred','unknown')),
  source_url       TEXT        NOT NULL,
  evidence_snippet TEXT        NOT NULL,
  is_primary       BOOLEAN     NOT NULL DEFAULT false,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.facility_contacts
  ADD CONSTRAINT fk_contacts_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
ALTER TABLE swim_sourcing.facility_contacts
  ADD CONSTRAINT fk_contacts_facility FOREIGN KEY (facility_id) REFERENCES swim_sourcing.facilities(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX ux_contacts_facility_email
  ON swim_sourcing.facility_contacts (facility_id, lower(email)) WHERE email IS NOT NULL;

-- ===========================================================================
-- Qualifications: transparent, reproducible scoring
-- ===========================================================================
-- score_breakdown holds the per-criterion contribution so a human can see WHY a
-- facility scored as it did. model_version makes a score reproducible: the same
-- inputs under the same version must produce the same number.
CREATE TABLE swim_sourcing.qualifications (
  id                UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id        UUID        NOT NULL,
  facility_id       UUID        NOT NULL,
  run_id            UUID,
  model_version     TEXT        NOT NULL,
  score             NUMERIC     NOT NULL CHECK (score >= 0 AND score <= 100),
  status            TEXT        NOT NULL
                      CHECK (status IN ('qualified','disqualified','needs_info')),
  completeness      NUMERIC     NOT NULL CHECK (completeness >= 0 AND completeness <= 1),
  score_breakdown   JSONB       NOT NULL,
  verified_fields   TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
  inferred_fields   TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
  unknown_fields    TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
  open_questions    JSONB       NOT NULL DEFAULT '[]'::jsonb,
  disqualifiers     TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.qualifications
  ADD CONSTRAINT fk_qual_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
ALTER TABLE swim_sourcing.qualifications
  ADD CONSTRAINT fk_qual_facility FOREIGN KEY (facility_id) REFERENCES swim_sourcing.facilities(id) ON DELETE RESTRICT;
CREATE INDEX ix_qual_facility ON swim_sourcing.qualifications (facility_id, created_at DESC);
CREATE INDEX ix_qual_company_score ON swim_sourcing.qualifications (company_id, score DESC);

-- ===========================================================================
-- Outreach: threads, messages, approvals
-- ===========================================================================
CREATE TABLE swim_sourcing.outreach_threads (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id       UUID        NOT NULL,
  facility_id      UUID        NOT NULL,
  contact_id       UUID,
  campaign_id      UUID        NOT NULL,
  provider         TEXT        NOT NULL DEFAULT 'gmail' CHECK (provider IN ('gmail','mock','resend')),
  provider_thread_id TEXT,
  subject          TEXT,
  state            TEXT        NOT NULL DEFAULT 'draft'
                     CHECK (state IN ('draft','approved','sent','awaiting_reply','replied',
                                      'escalated','closed_won','closed_lost','opted_out')),
  last_intent      TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.outreach_threads
  ADD CONSTRAINT fk_thread_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
ALTER TABLE swim_sourcing.outreach_threads
  ADD CONSTRAINT fk_thread_facility FOREIGN KEY (facility_id) REFERENCES swim_sourcing.facilities(id) ON DELETE RESTRICT;
-- One thread per facility per campaign: the first line of duplicate-outreach defence.
CREATE UNIQUE INDEX ux_thread_facility_campaign
  ON swim_sourcing.outreach_threads (facility_id, campaign_id);

-- Messages are append-only: a revision is a new row, never an edit. That is what
-- makes "the approved text is what was sent" verifiable after the fact.
CREATE TABLE swim_sourcing.outreach_messages (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id       UUID        NOT NULL,
  thread_id        UUID        NOT NULL,
  direction        TEXT        NOT NULL CHECK (direction IN ('outbound','inbound')),
  body             TEXT        NOT NULL,
  subject          TEXT,
  body_sha256      TEXT        NOT NULL,
  status           TEXT        NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','approved','sending','sent','failed','received')),
  -- Durable send state. send_attempt_id is generated BEFORE the provider call and
  -- reconciled against the provider afterwards: a network failure mid-send leaves
  -- 'sending' plus an attempt id, which reconciliation resolves by querying the
  -- provider for that id rather than blindly retrying. A unique index alone cannot
  -- give exactly-once delivery across a dropped connection.
  send_attempt_id  UUID,
  provider_message_id TEXT,
  provider_thread_id  TEXT,
  error            TEXT,
  approved_by      UUID,
  approved_at      TIMESTAMPTZ,
  sent_at          TIMESTAMPTZ,
  received_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.outreach_messages
  ADD CONSTRAINT fk_msg_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
ALTER TABLE swim_sourcing.outreach_messages
  ADD CONSTRAINT fk_msg_thread FOREIGN KEY (thread_id) REFERENCES swim_sourcing.outreach_threads(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX ux_msg_send_attempt
  ON swim_sourcing.outreach_messages (send_attempt_id) WHERE send_attempt_id IS NOT NULL;
CREATE UNIQUE INDEX ux_msg_provider_message
  ON swim_sourcing.outreach_messages (provider_message_id) WHERE provider_message_id IS NOT NULL;
CREATE INDEX ix_msg_thread ON swim_sourcing.outreach_messages (thread_id, created_at);
CREATE INDEX ix_msg_reconcile ON swim_sourcing.outreach_messages (status)
  WHERE status IN ('sending','approved');

-- Approvals bind a decision to an AUTHENTICATED identity and to the exact bytes
-- approved. approved_sha256 is compared against the message body at send time, so
-- editing an approved draft invalidates the approval.
CREATE TABLE swim_sourcing.approvals (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id       UUID        NOT NULL,
  subject_type     TEXT        NOT NULL
                     CHECK (subject_type IN ('campaign','message','reply','meeting','commercial_term')),
  subject_id       UUID        NOT NULL,
  decision         TEXT        NOT NULL CHECK (decision IN ('approved','rejected')),
  approved_sha256  TEXT,
  approver_user_id UUID        NOT NULL,
  approver_label   TEXT        NOT NULL,
  note             TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.approvals
  ADD CONSTRAINT fk_appr_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
CREATE INDEX ix_approvals_subject ON swim_sourcing.approvals (subject_type, subject_id, created_at DESC);

-- ===========================================================================
-- Meetings and suppression
-- ===========================================================================
CREATE TABLE swim_sourcing.meetings (
  id                UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id        UUID        NOT NULL,
  facility_id       UUID        NOT NULL,
  thread_id         UUID,
  status            TEXT        NOT NULL DEFAULT 'proposed'
                      CHECK (status IN ('proposed','scheduled','cancelled','completed')),
  starts_at         TIMESTAMPTZ,
  ends_at           TIMESTAMPTZ,
  timezone          TEXT        NOT NULL DEFAULT 'America/Chicago',
  location          TEXT,
  provider          TEXT        NOT NULL DEFAULT 'google_calendar'
                      CHECK (provider IN ('google_calendar','mock')),
  provider_event_id TEXT,
  attendees         JSONB       NOT NULL DEFAULT '[]'::jsonb,
  briefing          TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.meetings
  ADD CONSTRAINT fk_meet_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
ALTER TABLE swim_sourcing.meetings
  ADD CONSTRAINT fk_meet_facility FOREIGN KEY (facility_id) REFERENCES swim_sourcing.facilities(id) ON DELETE RESTRICT;
-- At most one scheduled meeting per facility: prevents double-booking a partner.
CREATE UNIQUE INDEX ux_meetings_one_scheduled
  ON swim_sourcing.meetings (facility_id) WHERE status = 'scheduled';
CREATE UNIQUE INDEX ux_meetings_provider_event
  ON swim_sourcing.meetings (provider_event_id) WHERE provider_event_id IS NOT NULL;

CREATE TABLE swim_sourcing.suppression_list (
  id          UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id  UUID        NOT NULL,
  email       TEXT        NOT NULL,
  reason      TEXT        NOT NULL
                CHECK (reason IN ('opt_out','bounce','complaint','manual','do_not_contact')),
  note        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.suppression_list
  ADD CONSTRAINT fk_supp_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX ux_suppression_company_email
  ON swim_sourcing.suppression_list (company_id, lower(email));

-- ===========================================================================
-- Durable job queue: lease + heartbeat + bounded retry
-- ===========================================================================
-- This is the generalisation of public.claim_intake_job, whose shortcoming was
-- that a crashed worker left a job 'running' forever with no way back. Here a
-- lease expires, a reaper returns the job to 'queued', attempts are counted, and
-- backoff is explicit.
CREATE TABLE swim_sourcing.jobs (
  id               UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id       UUID        NOT NULL,
  job_type         TEXT        NOT NULL
                     CHECK (job_type IN ('discover','enrich','qualify','draft_outreach',
                                         'send_outreach','poll_inbox','classify_reply',
                                         'schedule_meeting','reconcile_sends')),
  payload          JSONB       NOT NULL DEFAULT '{}'::jsonb,
  status           TEXT        NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued','running','done','failed','cancelled','blocked')),
  priority         INT         NOT NULL DEFAULT 100,
  attempts         INT         NOT NULL DEFAULT 0,
  max_attempts     INT         NOT NULL DEFAULT 3,
  next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_expires_at TIMESTAMPTZ,
  heartbeat_at     TIMESTAMPTZ,
  worker_id        TEXT,
  run_id           UUID,
  result           JSONB,
  error            TEXT,
  cancel_requested BOOLEAN     NOT NULL DEFAULT false,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at       TIMESTAMPTZ,
  finished_at      TIMESTAMPTZ,
  PRIMARY KEY (id)
);
ALTER TABLE swim_sourcing.jobs
  ADD CONSTRAINT fk_jobs_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;
CREATE INDEX ix_jobs_claimable ON swim_sourcing.jobs (status, next_attempt_at, priority);
CREATE INDEX ix_jobs_company ON swim_sourcing.jobs (company_id, created_at DESC);
CREATE INDEX ix_jobs_lease ON swim_sourcing.jobs (status, lease_expires_at)
  WHERE status = 'running';

-- ===========================================================================
-- RLS: tenant-scoped, bound to verified membership
-- ===========================================================================
-- These predicates use auth.uid() via company_members - NOT a caller-supplied
-- parameter and NOT a session GUC set from an argument. That is the difference
-- between isolation and self-declared tenancy.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['facilities','facility_contacts','qualifications',
                           'outreach_threads','outreach_messages','approvals',
                           'meetings','suppression_list','jobs']
  LOOP
    EXECUTE format('ALTER TABLE swim_sourcing.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format($f$
      CREATE POLICY tenant_member_select ON swim_sourcing.%I
        FOR SELECT TO authenticated
        USING (company_id IN (SELECT company_id FROM public.company_members
                              WHERE user_id = auth.uid()))$f$, t);
    EXECUTE format($f$
      CREATE POLICY service_role_all ON swim_sourcing.%I
        FOR ALL TO service_role USING (true) WITH CHECK (true)$f$, t);
  END LOOP;
END $$;

-- Append-only enforcement that binds service_role too (same rationale as 048).
CREATE TRIGGER trg_outreach_messages_no_delete
  BEFORE DELETE ON swim_sourcing.outreach_messages
  FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation();
CREATE TRIGGER trg_approvals_immutable
  BEFORE UPDATE OR DELETE ON swim_sourcing.approvals
  FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation();

COMMIT;
