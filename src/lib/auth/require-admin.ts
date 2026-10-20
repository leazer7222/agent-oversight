import { requireTenant, AuthError, logPrivilegedAction } from './require-tenant'

/**
 * Guard for the legacy platform-oversight routes.
 *
 * These 26 routes aggregate operational data ACROSS companies by design -
 * /api/hierarchy walks every company, /api/cost aggregates all spend,
 * /api/runs and /api/errors are platform-wide. They predate requireTenant and
 * accepted an optional `?company=` filter, which is a presentation convenience,
 * not an authorization boundary.
 *
 * Scoping them per-tenant would be the wrong fix: their purpose IS the
 * cross-company view. The correct and smallest fix is to require a platform
 * administrator, because no tenant user should ever call them - a tenant's data
 * reaches them through /api/sourcing/*, which is tenant-scoped.
 *
 * Returns a Response to return immediately, or null to proceed. A non-throwing
 * shape was chosen deliberately: these routes have no try/catch, so a throwing
 * guard would surface as an unhandled 500 instead of a clean 401/403.
 */
export async function requireAdminOrDeny(
  request?: Request
): Promise<Response | null> {
  try {
    const ctx = await requireTenant(null)

    if (ctx.role !== 'admin') {
      await logPrivilegedAction({
        actorUserId: ctx.userId,
        actorLabel: ctx.email ?? ctx.userId,
        action: 'legacy_route_denied',
        companyId: ctx.companyId,
        target: request ? new URL(request.url).pathname : null,
        detail: { role: ctx.role, reason: 'platform-oversight route requires admin' },
      })
      return Response.json(
        {
          error: 'Forbidden',
          detail:
            'this platform-oversight endpoint requires an administrator. ' +
            'Tenant-scoped data is available under /api/sourcing/.',
        },
        { status: 403 }
      )
    }

    return null
  } catch (err) {
    if (err instanceof AuthError) {
      return Response.json({ error: err.message, detail: err.detail },
                           { status: err.status })
    }
    console.error('[require-admin] unexpected error:', err)
    return Response.json({ error: 'Internal error' }, { status: 500 })
  }
}
