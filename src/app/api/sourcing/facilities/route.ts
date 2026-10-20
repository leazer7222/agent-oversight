import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { requireTenant, authErrorResponse } from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/**
 * GET /api/sourcing/facilities?stage=&limit=
 *
 * Tenant comes from requireTenant(), not from a query parameter. `?company=` is
 * accepted only so that a mismatch can be REJECTED rather than silently
 * ignored; an operator asking for another company's id gets a 403.
 */
export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const ctx = await requireTenant(url.searchParams.get('company'))

    const stage = url.searchParams.get('stage')
    const limit = Number(url.searchParams.get('limit') ?? 100)

    const sb = createServiceRoleClient()
    const { data, error } = await sb.rpc('swim_list_facilities', {
      p_company_id: ctx.companyId,
      p_stage: stage,
      p_limit: Number.isFinite(limit) ? limit : 100,
    })
    if (error) return Response.json({ error: error.message }, { status: 500 })

    return Response.json({
      company_id: ctx.companyId,
      role: ctx.role,
      cross_tenant: ctx.isCrossTenant,
      count: (data ?? []).length,
      facilities: data ?? [],
    })
  } catch (err) {
    return authErrorResponse(err)
  }
}
