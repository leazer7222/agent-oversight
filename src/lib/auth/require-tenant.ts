import { createClient, createServiceRoleClient } from '@/lib/supabase/server'

/**
 * Verified tenant context for an API route.
 *
 * The rule this enforces: a company_id arriving in a query string or a request
 * body is an ASSERTION, never an authorization. Tenant identity comes from the
 * session, via public.company_members. If a request also carries ?company=, it
 * must agree with the session - a mismatch is a 403, not a silent override.
 *
 * Platform administrators (role='admin') may act across tenants, because the
 * oversight dashboard needs it. Every such cross-tenant access writes a row to
 * public.privileged_action_log, so the capability is audited rather than
 * implicit.
 */

export type TenantRole = 'owner' | 'operator' | 'admin'

export interface TenantContext {
  userId: string
  email: string | null
  companyId: string
  role: TenantRole
  /** True when an admin is acting outside their own company's rows. */
  isCrossTenant: boolean
}

export class AuthError extends Error {
  constructor(message: string, readonly status: number, readonly detail?: string) {
    super(message)
  }
}

export function authErrorResponse(err: unknown): Response {
  if (err instanceof AuthError) {
    return Response.json({ error: err.message, detail: err.detail }, { status: err.status })
  }
  console.error('[auth] unexpected error:', err)
  return Response.json({ error: 'Internal error' }, { status: 500 })
}

interface Membership {
  company_id: string
  role: TenantRole
}

/**
 * Resolve the acting tenant, or throw.
 *
 * @param requestedCompanyId Optional company the caller asked for (from a query
 *   param or body). Checked against the session; never trusted on its own.
 */
export async function requireTenant(
  requestedCompanyId?: string | null
): Promise<TenantContext> {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()

  if (error || !user) {
    throw new AuthError('Unauthorized', 401, 'no authenticated session')
  }

  // Read memberships with the service role. RLS on company_members would also
  // permit the user to read their own rows, but going through the service role
  // keeps this independent of policy drift on that table.
  const admin = createServiceRoleClient()
  const { data, error: memErr } = await admin
    .from('company_members')
    .select('company_id, role')
    .eq('user_id', user.id)

  if (memErr) {
    throw new AuthError('Internal error', 500, memErr.message)
  }

  const memberships = (data ?? []) as Membership[]
  if (memberships.length === 0) {
    throw new AuthError('Forbidden', 403,
      'this account is not a member of any company')
  }

  const adminMembership = memberships.find((m) => m.role === 'admin')

  // No explicit company requested: use the only one, or the admin's own.
  if (!requestedCompanyId) {
    const chosen = memberships[0]
    return {
      userId: user.id,
      email: user.email ?? null,
      companyId: chosen.company_id,
      role: chosen.role,
      isCrossTenant: false,
    }
  }

  const direct = memberships.find((m) => m.company_id === requestedCompanyId)
  if (direct) {
    return {
      userId: user.id,
      email: user.email ?? null,
      companyId: direct.company_id,
      role: direct.role,
      isCrossTenant: false,
    }
  }

  // Requested a company the user is not a member of. Only an admin may proceed,
  // and the access is recorded.
  if (adminMembership) {
    await logPrivilegedAction({
      actorUserId: user.id,
      actorLabel: user.email ?? user.id,
      action: 'cross_tenant_access',
      companyId: requestedCompanyId,
      detail: { via: 'admin_role', requested: requestedCompanyId },
    })
    return {
      userId: user.id,
      email: user.email ?? null,
      companyId: requestedCompanyId,
      role: 'admin',
      isCrossTenant: true,
    }
  }

  // The important case: an operator of company A asking for company B.
  throw new AuthError('Forbidden', 403,
    'the requested company does not match your session')
}

/** Require a minimum role. owner and admin both outrank operator. */
export function requireRole(ctx: TenantContext, allowed: TenantRole[]): void {
  if (!allowed.includes(ctx.role)) {
    throw new AuthError('Forbidden', 403,
      `this action requires one of: ${allowed.join(', ')}`)
  }
}

export async function logPrivilegedAction(entry: {
  actorUserId?: string | null
  actorLabel: string
  action: string
  companyId?: string | null
  target?: string | null
  detail?: Record<string, unknown>
}): Promise<void> {
  try {
    const admin = createServiceRoleClient()
    await admin.from('privileged_action_log').insert({
      actor_user_id: entry.actorUserId ?? null,
      actor_label: entry.actorLabel,
      action: entry.action,
      company_id: entry.companyId ?? null,
      target: entry.target ?? null,
      detail: entry.detail ?? {},
    })
  } catch (err) {
    // Audit failure must not break the request, but it must be visible.
    console.error('[audit] failed to write privileged_action_log:', err)
  }
}
