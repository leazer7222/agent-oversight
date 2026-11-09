import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import {
  requireTenant, requireRole, authErrorResponse, logPrivilegedAction,
} from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/**
 * POST /api/sourcing/suppress
 * Body: { email, note?, company? }
 *
 * "Do not contact this address again." Adds the address to the company's
 * suppression list (reason do_not_contact) and marks its threads opted_out.
 * The send chokepoint refuses suppressed recipients and redrafting skips
 * them, so this is the one switch that makes a facility untouchable.
 */
export async function POST(request: NextRequest) {
  try {
    const payload = await request.json().catch(() => ({}))
    const ctx = await requireTenant(payload.company ?? null)
    requireRole(ctx, ['owner', 'operator', 'admin'])

    const email = String(payload.email ?? '').trim()
    if (!email || !email.includes('@')) {
      return Response.json({ error: 'a valid email is required' }, { status: 400 })
    }

    const sb = createServiceRoleClient()
    const { data, error } = await sb.rpc('swim_add_suppression', {
      p_company_id: ctx.companyId,
      p_email: email,
      p_reason: 'do_not_contact',
      p_note: typeof payload.note === 'string' && payload.note.trim()
        ? `${payload.note.trim()} (by ${ctx.email ?? ctx.userId})`
        : `by ${ctx.email ?? ctx.userId}`,
    })
    if (error) return Response.json({ error: error.message }, { status: 500 })

    await logPrivilegedAction({
      actorUserId: ctx.userId,
      actorLabel: ctx.email ?? ctx.userId,
      action: 'suppress_contact',
      companyId: ctx.companyId,
      target: `email:${email.toLowerCase()}`,
      detail: { suppression_id: data },
    })

    return Response.json({ ok: true, suppression_id: data })
  } catch (err) {
    return authErrorResponse(err)
  }
}
