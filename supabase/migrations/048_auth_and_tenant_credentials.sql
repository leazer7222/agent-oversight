-- Migration 048: P0-1 authentication/RBAC + P0-2 tenant provider credentials
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 001 (companies), 047 (hardening - this migration assumes anon/
--             authenticated hold no blanket grants and that the global default
--             privileges deny PUBLIC execute on new functions).
-- Status: AUTHORED, NOT APPLIED.
--
-- Two concerns, one migration, because they share the tenant-resolution helper:
--   P0-1  public.company_members  - who may act for which company, in what role
--   P0-2  platform.tenant_provider_credentials - per-tenant LLM API keys
--
-- SECURITY NOTE ON CREDENTIAL STORAGE
-- Ciphertext only. The plaintext key never enters the database, never appears in
-- a log line, and is never returned by any function here. Encryption happens in
-- the application (AES-256-GCM, key from CREDENTIAL_ENCRYPTION_KEY, which lives
-- in the deployment environment and NOT in this repo). The database stores the
-- ciphertext, the nonce, a SHA-256 fingerprint for equality checks, and the last
-- four characters for display. There is deliberately NO function that returns a
-- decrypted key: decryption is the worker's job, after it has resolved a tenant.

BEGIN;

-- ===========================================================================
-- P0-1: company membership and roles
-- ===========================================================================
CREATE TABLE public.company_members (
  id          UUID        NOT NULL DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL,
  company_id  UUID        NOT NULL,
  role        TEXT        NOT NULL CHECK (role IN ('owner', 'operator', 'admin')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by  TEXT,
  PRIMARY KEY (id)
);

ALTER TABLE public.company_members
  ADD CONSTRAINT fk_company_members_user
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT;
ALTER TABLE public.company_members
  ADD CONSTRAINT fk_company_members_company
  FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX ux_company_members_user_company
  ON public.company_members (user_id, company_id);
CREATE INDEX ix_company_members_user ON public.company_members (user_id);
CREATE INDEX ix_company_members_company ON public.company_members (company_id, role);

COMMENT ON TABLE public.company_members IS
  'Maps an authenticated auth.users identity to a company and a role. This is the '
  'ONLY authority for tenant context; a company_id supplied in a request body or '
  'query string is never trusted. role=admin is the platform administrator and may '
  'read across companies, which is audited.';

ALTER TABLE public.company_members ENABLE ROW LEVEL SECURITY;

-- A member may read their own membership rows. Nothing else is exposed to
-- authenticated; all writes go through the service role in server routes.
CREATE POLICY own_membership_select ON public.company_members
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());
CREATE POLICY service_role_all ON public.company_members
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ===========================================================================
-- P0-1: tenant resolution + audit
-- ===========================================================================
-- Returns the companies the CURRENT authenticated user may act for. Bound to
-- auth.uid(), so it cannot be influenced by a caller-supplied parameter - this
-- is the fix for the caller-asserted-tenant problem (P0-0D).
CREATE OR REPLACE FUNCTION public.current_user_companies()
RETURNS TABLE (company_id UUID, role TEXT)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
STABLE
AS $$
  SELECT cm.company_id, cm.role
  FROM public.company_members cm
  WHERE cm.user_id = auth.uid();
$$;

REVOKE ALL ON FUNCTION public.current_user_companies() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.current_user_companies() TO authenticated, service_role;

-- Append-only audit of privileged operations: admin cross-tenant reads,
-- credential writes, approval decisions, outbound sends.
CREATE TABLE public.privileged_action_log (
  id            UUID        NOT NULL DEFAULT gen_random_uuid(),
  actor_user_id UUID,
  actor_label   TEXT        NOT NULL,
  action        TEXT        NOT NULL,
  company_id    UUID,
  target        TEXT,
  detail        JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);
CREATE INDEX ix_privileged_action_log_company
  ON public.privileged_action_log (company_id, created_at DESC);
CREATE INDEX ix_privileged_action_log_action
  ON public.privileged_action_log (action, created_at DESC);

COMMENT ON TABLE public.privileged_action_log IS
  'Append-only audit of privileged operations. Never updated or deleted - see the '
  'immutability trigger below, which binds even the service role.';

ALTER TABLE public.privileged_action_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY service_role_insert ON public.privileged_action_log
  FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY service_role_select ON public.privileged_action_log
  FOR SELECT TO service_role USING (true);

-- ===========================================================================
-- P0-1g: ledger immutability that binds service_role
-- ===========================================================================
-- RLS does NOT constrain service_role (BYPASSRLS), so migration 047 could stop
-- authenticated mutation of the ledger but not service-role mutation. A trigger
-- runs regardless of role and is the only mechanism that closes that gap.
CREATE OR REPLACE FUNCTION public.forbid_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION
    'append-only: % on %.% is forbidden (ledger immutability, P0-1g)',
    TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;

REVOKE ALL ON FUNCTION public.forbid_mutation() FROM PUBLIC, anon, authenticated;

CREATE TRIGGER trg_agent_outputs_append_only
  BEFORE UPDATE OR DELETE ON public.agent_outputs
  FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation();
CREATE TRIGGER trg_agent_events_append_only
  BEFORE UPDATE OR DELETE ON public.agent_events
  FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation();
CREATE TRIGGER trg_privileged_action_log_append_only
  BEFORE UPDATE OR DELETE ON public.privileged_action_log
  FOR EACH ROW EXECUTE FUNCTION public.forbid_mutation();

-- NOTE: public.audit_log is deliberately NOT given this trigger yet. It is
-- currently unused by application code (zero writers found), and attaching an
-- append-only trigger to a table whose write pattern is unknown risks breaking a
-- caller discovered later. privileged_action_log is the audited surface going
-- forward. Revisit audit_log once its writers are confirmed or it is dropped.
--
-- public.runs is also excluded: the ingest endpoint legitimately UPDATEs a run
-- row to move it from 'started' to 'completed'/'failed'. Runs are a lifecycle
-- record, not an append-only artifact; agent_events is the immutable log.

-- ===========================================================================
-- P0-2: tenant provider credentials
-- ===========================================================================
CREATE TABLE platform.tenant_provider_credentials (
  id              UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id      UUID        NOT NULL,
  provider        TEXT        NOT NULL CHECK (provider IN ('anthropic', 'openai', 'google')),
  key_ciphertext  BYTEA       NOT NULL,
  key_nonce       BYTEA       NOT NULL,
  key_fingerprint TEXT        NOT NULL,
  key_last4       TEXT        NOT NULL,
  status          TEXT        NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'revoked', 'invalid')),
  label           TEXT,
  validated_at    TIMESTAMPTZ,
  validation_error TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by      TEXT,
  revoked_at      TIMESTAMPTZ,
  PRIMARY KEY (id)
);

ALTER TABLE platform.tenant_provider_credentials
  ADD CONSTRAINT fk_tpc_company
  FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;

-- At most one ACTIVE credential per (company, provider). Rotation = insert the
-- new row, then mark the old one revoked. Partial index because revoked rows
-- must be retained for audit.
CREATE UNIQUE INDEX ux_tpc_active_company_provider
  ON platform.tenant_provider_credentials (company_id, provider)
  WHERE status = 'active';
CREATE INDEX ix_tpc_company ON platform.tenant_provider_credentials (company_id, provider, status);

COMMENT ON TABLE platform.tenant_provider_credentials IS
  'Per-tenant LLM provider credentials, stored as AES-256-GCM ciphertext. The '
  'plaintext key is never stored, logged, or returned by any database function. '
  'Decryption happens in the worker after tenant resolution.';

ALTER TABLE platform.tenant_provider_credentials ENABLE ROW LEVEL SECURITY;
CREATE POLICY service_role_all ON platform.tenant_provider_credentials
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Public accessor returning CIPHERTEXT, for the worker (service_role) only.
-- PostgREST does not expose the platform schema, so a public SECURITY DEFINER
-- function is the established pattern in this codebase for cross-schema reads.
-- Deliberately NOT granted to authenticated: a browser session must never be
-- able to retrieve credential material, even encrypted.
CREATE OR REPLACE FUNCTION public.get_tenant_credential(
  p_company_id UUID,
  p_provider   TEXT
)
RETURNS TABLE (
  credential_id   UUID,
  key_ciphertext  BYTEA,
  key_nonce       BYTEA,
  key_fingerprint TEXT,
  key_last4       TEXT
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, platform, public
STABLE
AS $$
  SELECT id, key_ciphertext, key_nonce, key_fingerprint, key_last4
  FROM platform.tenant_provider_credentials
  WHERE company_id = p_company_id
    AND provider   = p_provider
    AND status     = 'active'
  LIMIT 1;
$$;

REVOKE ALL ON FUNCTION public.get_tenant_credential(UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_tenant_credential(UUID, TEXT) TO service_role;

-- Metadata-only view for the dashboard: never exposes ciphertext.
CREATE OR REPLACE FUNCTION public.list_tenant_credentials(p_company_id UUID)
RETURNS TABLE (
  credential_id UUID,
  provider      TEXT,
  status        TEXT,
  key_last4     TEXT,
  label         TEXT,
  validated_at  TIMESTAMPTZ,
  validation_error TEXT,
  created_at    TIMESTAMPTZ
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, platform, public
STABLE
AS $$
  SELECT id, provider, status, key_last4, label, validated_at, validation_error, created_at
  FROM platform.tenant_provider_credentials
  WHERE company_id = p_company_id
  ORDER BY created_at DESC;
$$;

REVOKE ALL ON FUNCTION public.list_tenant_credentials(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.list_tenant_credentials(UUID) TO service_role;

-- ===========================================================================
-- P0-3: fail-closed tenant spend ceiling
-- ===========================================================================
-- First ENFORCING use of the budget data. Scoped by company so a bug cannot
-- stall ReformAI's agents: a company with no cost_limit_usd set is unlimited,
-- preserving today's behaviour for existing tenants.
CREATE OR REPLACE FUNCTION public.check_tenant_budget(
  p_company_id   UUID,
  p_estimate_usd NUMERIC DEFAULT 0
)
RETURNS TABLE (allowed BOOLEAN, reason TEXT, spent_usd NUMERIC, limit_usd NUMERIC)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
STABLE
AS $$
DECLARE
  v_limit  NUMERIC;
  v_period TEXT;
  v_spent  NUMERIC;
  v_since  TIMESTAMPTZ;
BEGIN
  SELECT c.cost_limit_usd, coalesce(c.cost_limit_period, 'monthly')
    INTO v_limit, v_period
  FROM public.companies c WHERE c.id = p_company_id;

  IF NOT FOUND THEN
    RETURN QUERY SELECT false, 'unknown_company', 0::NUMERIC, 0::NUMERIC;
    RETURN;
  END IF;

  IF v_limit IS NULL THEN
    RETURN QUERY SELECT true, 'no_limit_configured', 0::NUMERIC, NULL::NUMERIC;
    RETURN;
  END IF;

  v_since := CASE WHEN v_period = 'daily'  THEN date_trunc('day', now())
                  WHEN v_period = 'weekly' THEN date_trunc('week', now())
                  ELSE date_trunc('month', now()) END;

  SELECT coalesce(sum(r.cost_usd), 0) INTO v_spent
  FROM public.runs r
  JOIN public.agents a ON a.id = r.agent_id
  WHERE a.company_id = p_company_id
    AND r.started_at >= v_since;

  IF v_spent + coalesce(p_estimate_usd, 0) > v_limit THEN
    RETURN QUERY SELECT false, 'budget_exceeded', v_spent, v_limit;
  ELSE
    RETURN QUERY SELECT true, 'ok', v_spent, v_limit;
  END IF;
END $$;

REVOKE ALL ON FUNCTION public.check_tenant_budget(UUID, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_tenant_budget(UUID, NUMERIC) TO service_role;

COMMIT;
