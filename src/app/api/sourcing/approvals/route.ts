import type { NextRequest } from 'next/server'
import { createHash } from 'node:crypto'
import { createServiceRoleClient } from '@/lib/supabase/server'
import {
  requireTenant, requireRole, authErrorResponse, logPrivilegedAction,
} from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/**
 * POST /api/sourcing/approvals
 * Body: { subject_type, subject_id, decision, note? }
 *
 * The approval gate for outbound email. Two properties make it meaningful,
 * neither of which the previous gate-a pattern had:
 *
 *  1. The approver identity comes from the SESSION. The old pattern took
 *     `ratified_by` as a free-text body field, so anyone who could reach the URL
 *     could approve as anyone.
 *  2. The decision is bound to a CONTENT HASH of the exact message body. Editing
 *     an approved draft changes the hash and voids the approval, so an injected
 *     instruction cannot append terms to something already approved.
 */
function sha256(text: string): string {
  return createHash('sha256').update(text.replace(/\r\n/g, '\n').trim()).digest('hex')
}

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

    // For a message approval, hash the CURRENT body so the approval binds bytes.
    let approvedSha: string | null = null
    if (subject_type === 'message') {
      const { data: msg, error } = await sb
        .schema('swim_sourcing')
        .from('outreach_messages')
        .select('id, body, company_id, status')
        .eq('id', subject_id)
        .single()
      if (error || !msg) {
        return Response.json({ error: 'message not found' }, { status: 404 })
      }
      if (msg.company_id !== ctx.companyId) {
        // Belt and braces: the RPC path already scopes by tenant, but an
        // approval is exactly where a cross-tenant mistake would matter most.
        return Response.json({ error: 'Forbidden' }, { status: 403 })
      }
      approvedSha = sha256(msg.body as string)
    }

    const { data: approval, error: insErr } = await sb
      .schema('swim_sourcing')
      .from('approvals')
      .insert({
        company_id: ctx.companyId,
        subject_type,
        subject_id,
        decision,
        approved_sha256: approvedSha,
        approver_user_id: ctx.userId,
        approver_label: ctx.email ?? ctx.userId,
        note: note ?? null,
      })
      .select('id, created_at')
      .single()

    if (insErr) return Response.json({ error: insErr.message }, { status: 500 })

    if (decision === 'approved' && subject_type === 'message') {
      await sb.schema('swim_sourcing').from('outreach_messages')
        .update({ status: 'approved', approved_by: ctx.userId, approved_at: new Date().toISOString() })
        .eq('id', subject_id)
    }

    await logPrivilegedAction({
      actorUserId: ctx.userId,
      actorLabel: ctx.email ?? ctx.userId,
      action: `approval_${decision}`,
      companyId: ctx.companyId,
      target: `${subject_type}:${subject_id}`,
      detail: { approved_sha256: approvedSha },
    })

    return Response.json({
      ok: true,
      approval_id: approval?.id,
      approved_sha256: approvedSha,
      approver: ctx.email ?? ctx.userId,
    })
  } catch (err) {
    return authErrorResponse(err)
  }
}
