import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import {
  requireTenant, requireRole, authErrorResponse, logPrivilegedAction,
} from '@/lib/auth/require-tenant'

export const runtime = 'nodejs'

/**
 * POST /api/sourcing/jobs
 * Body: { job_type, payload?, company? }
 *
 * Enqueues work for the swim-sourcing worker on behalf of a signed-in owner or
 * operator. Enqueueing is not executing: the worker still runs preflight (kill
 * switch, budget, credential) and, for send_outreach, the database chokepoint
 * and the recipient allow-list. Job types are whitelisted here so a browser
 * cannot enqueue anything the worker was not designed to be asked for.
 */
const ALLOWED_JOB_TYPES = new Set([
  'discover', 'enrich', 'qualify', 'draft_outreach', 'poll_inbox', 'classify_reply',
  'send_outreach', 'reconcile_sends',
])

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}))
    const ctx = await requireTenant(body.company ?? null)
    requireRole(ctx, ['owner', 'operator', 'admin'])

    const jobType = String(body.job_type ?? '')
    if (!ALLOWED_JOB_TYPES.has(jobType)) {
      return Response.json({ error: `job_type must be one of ${[...ALLOWED_JOB_TYPES].join(', ')}` }, { status: 400 })
    }
    const payload = body.payload && typeof body.payload === 'object' ? body.payload : {}

    const sb = createServiceRoleClient()
    const { data, error } = await sb.rpc('swim_enqueue_job', {
      p_company_id: ctx.companyId,
      p_job_type: jobType,
      p_payload: { ...payload, enqueued_by: ctx.email ?? ctx.userId },
    })
    if (error) return Response.json({ error: error.message }, { status: 500 })

    await logPrivilegedAction({
      actorUserId: ctx.userId,
      actorLabel: ctx.email ?? ctx.userId,
      action: `enqueue_${jobType}`,
      companyId: ctx.companyId,
      target: `job:${data}`,
      detail: { payload },
    })

    return Response.json({ ok: true, job_id: data, job_type: jobType })
  } catch (err) {
    return authErrorResponse(err)
  }
}
