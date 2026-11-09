import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import {
  requireTenant, requireRole, authErrorResponse, logPrivilegedAction,
} from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/**
 * POST /api/sourcing/drafts
 * Body: { message_id, body, subject?, note?, company? }
 *
 * Rewrites an UNSENT outbound draft. The database function keeps the previous
 * text in swim_sourcing.message_revisions, drops the message back to 'draft'
 * and voids any approval (the send chokepoint re-checks the approval hash at
 * send time anyway). The unsubscribe line must survive the edit. Sent messages
 * cannot be edited. Goes through a public RPC because PostgREST does not expose
 * swim_sourcing.
 */
export async function POST(request: NextRequest) {
  try {
    const payload = await request.json().catch(() => ({}))
    const ctx = await requireTenant(payload.company ?? null)
    requireRole(ctx, ['owner', 'operator', 'admin'])

    const messageId = String(payload.message_id ?? '')
    const body = typeof payload.body === 'string' ? payload.body : ''
    if (!messageId || !body.trim()) {
      return Response.json({ error: 'message_id and body are required' }, { status: 400 })
    }

    const sb = createServiceRoleClient()
    const { data, error } = await sb.rpc('swim_update_draft', {
      p_company_id: ctx.companyId,
      p_payload: {
        message_id: messageId,
        subject: typeof payload.subject === 'string' ? payload.subject : null,
        body,
        editor_user_id: ctx.userId,
        editor_label: ctx.email ?? ctx.userId,
        note: typeof payload.note === 'string' ? payload.note : null,
      },
    })
    if (error) {
      const notFound = /not found/i.test(error.message)
      const refused = /cannot be edited|too short|unsubscribe/i.test(error.message)
      return Response.json({ error: error.message }, { status: notFound ? 404 : refused ? 422 : 500 })
    }

    await logPrivilegedAction({
      actorUserId: ctx.userId,
      actorLabel: ctx.email ?? ctx.userId,
      action: 'edit_draft',
      companyId: ctx.companyId,
      target: `message:${messageId}`,
      detail: { changed: (data as { changed?: boolean } | null)?.changed ?? null },
    })

    return Response.json({ ok: true, ...(data as Record<string, unknown>) })
  } catch (err) {
    return authErrorResponse(err)
  }
}
