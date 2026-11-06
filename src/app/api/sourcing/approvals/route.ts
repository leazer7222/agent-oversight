import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import {
  requireTenant, requireRole, authErrorResponse, logPrivilegedAction,
} from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/**
 * POST /api/sourcing/approvals
 * Body: { subject_type, subject_id, decision, note?, company? }
 *
 * The approval gate for outbound email. Two properties make it meaningful:
 *
 *  1. The approver identity comes from the SESSION (requireTenant), never from
 *     the request body.
 *  2. For a message, the decision is bound to a CONTENT HASH of the body as it
 *     stands in the database at approval time. The hash is computed inside
 *     public.swim_record_approval, and public.swim_authorize_send compares it
 *     again at send time - so editing an approved draft voids the approval.
 *
 * Goes through a public RPC because PostgREST does not expose swim_sourcing
 * (a direct .schema('swim_sourcing') call returns PGRST106).
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}))
    const ctx = await requireTenant(body.company ?? null)
    requireRole(ctx, ['owner', 'operator', 'admin'])

    const { subject_type, subject_id, decision, note } = body
    if (!subject_type || !subject_id || !decision) {
      return Response.json(
        { error: 'subject_type, subject_id and decision are required' }, { status: 400 })
    }
    if (!['approved', 'rejected'].includes(decision)) {
      return Response.json({ error: 'decision must be approved or rejected' }, { status: 400 })
    }

    const sb = createServiceRoleClient()
    const { data, error } = await sb.rpc('swim_record_approval', {
      p_company_id: ctx.companyId,
      p_payload: {
        subject_type, subject_id, decision,
        approver_user_id: ctx.userId,
        approver_label: ctx.email ?? ctx.userId,
        note: note ?? null,
      },
    })
    if (error) {
      const notFound = /not found/i.test(error.message)
      return Response.json({ error: error.message }, { status: notFound ? 404 : 500 })
    }
    const result = (data ?? {}) as { approval_id?: string; approved_sha256?: string | null }

    await logPrivilegedAction({
      actorUserId: ctx.userId,
      actorLabel: ctx.email ?? ctx.userId,
      action: `approval_${decision}`,
      companyId: ctx.companyId,
      target: `${subject_type}:${subject_id}`,
      detail: { approved_sha256: result.approved_sha256 ?? null },
    })

    return Response.json({
      ok: true,
      approval_id: result.approval_id,
      approved_sha256: result.approved_sha256 ?? null,
      approver: ctx.email ?? ctx.userId,
    })
  } catch (err) {
    return authErrorResponse(err)
  }
}
