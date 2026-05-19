import type { NextRequest } from 'next/server'
import { z } from 'zod'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

// RFC-003 §3 event envelope schema
const EventEnvelopeSchema = z.object({
  event_id:        z.string().uuid(),
  schema_version:  z.string().min(1),
  event_type:      z.string().min(1),
  emitted_at:      z.string().datetime(),
  sequence_number: z.number().int().optional().nullable(),
  trace_id:        z.string().uuid(),
  run_id:          z.string().uuid().optional().nullable(),
  parent_run_id:   z.string().uuid().optional().nullable(),
  campaign_id:     z.string().uuid().optional().nullable(),
  tenant_id:       z.string().uuid(),
  is_replay:       z.boolean(),
  replay_id:       z.string().uuid().optional().nullable(),
  payload:         z.record(z.string(), z.unknown()),
})

export async function POST(request: NextRequest) {
  // Auth — same secret pattern as /api/ingest
  const secret = request.headers.get('x-agent-secret')
  if (!secret || secret !== process.env.INGEST_SECRET) {
    return Response.json(
      { status: 'rejected', reason: 'unauthorized' },
      { status: 401 }
    )
  }

  // Parse
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json(
      { status: 'rejected', reason: 'schema_validation_failed' },
      { status: 400 }
    )
  }

  // Validate against RFC-003 §3 envelope
  const parsed = EventEnvelopeSchema.safeParse(body)
  if (!parsed.success) {
    return Response.json(
      { status: 'rejected', reason: 'schema_validation_failed' },
      { status: 400 }
    )
  }

  const ev = parsed.data
  const supabase = createServiceRoleClient()

  // Write via public SECURITY DEFINER RPC — accesses telemetry schema from inside Postgres.
  // Returns true if newly inserted, false if duplicate (ON CONFLICT idempotency, RFC-003 §6).
  const { data: isNew, error } = await supabase.rpc('ingest_telemetry_event', {
    p_id:              ev.event_id,
    p_event_type:      ev.event_type,
    p_schema_version:  ev.schema_version,
    p_emitted_at:      ev.emitted_at,
    p_sequence_number: ev.sequence_number ?? null,
    p_trace_id:        ev.trace_id,
    p_run_id:          ev.run_id ?? null,
    p_parent_run_id:   ev.parent_run_id ?? null,
    p_campaign_id:     ev.campaign_id ?? null,
    p_tenant_id:       ev.tenant_id,
    p_is_replay:       ev.is_replay,
    p_replay_id:       ev.replay_id ?? null,
    p_payload:         ev.payload,
  })

  if (error) {
    console.error('[telemetry/ingest] rpc failed:', error.message, { event_id: ev.event_id })
    return Response.json({ status: 'error' }, { status: 500 })
  }

  if (isNew === false) {
    return Response.json({ status: 'accepted', event_id: ev.event_id, duplicate: true }, { status: 200 })
  }

  // Fan-out to consumers is async and happens after the INSERT commits.
  // Phase 1: no consumers yet. Fan-out wired in Phase 1 Group 5 (evaluation pipeline).
  // Do NOT await fan-out here — it must never block the ingest response (RFC-003 §10).

  return Response.json(
    { status: 'accepted', event_id: ev.event_id, duplicate: false },
    { status: 200 }
  )
}
