-- Migration 052: current_user_companies() becomes SECURITY INVOKER
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 048 (created the function), 051 (granted authenticated SELECT)
-- Status: APPLIED 2026-10-20
--
-- 048 created it SECURITY DEFINER because, at that point, authenticated had no
-- grant on company_members (047 had revoked the blanket grants) and the
-- function could not otherwise read the table. It filtered on auth.uid() in its
-- own body.
--
-- 051 granted authenticated SELECT on company_members, where the
-- own_membership_select RLS policy already restricts rows to
-- user_id = auth.uid(). The definer privilege is therefore no longer needed,
-- and dropping it is a genuine improvement rather than lint-chasing: row
-- filtering moves from "this function remembers to add a WHERE clause" to "the
-- database enforces it", so a future edit to the body cannot widen it.
--
-- Also clears the last advisor WARN
-- (authenticated_security_definer_function_executable).

BEGIN;

CREATE OR REPLACE FUNCTION public.current_user_companies()
RETURNS TABLE (company_id UUID, role TEXT)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, public
STABLE
AS $$
  -- WHERE retained as defence in depth; own_membership_select enforces the
  -- same restriction independently.
  SELECT cm.company_id, cm.role
  FROM public.company_members cm
  WHERE cm.user_id = auth.uid();
$$;

REVOKE ALL ON FUNCTION public.current_user_companies() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.current_user_companies() TO authenticated, service_role;

COMMIT;
