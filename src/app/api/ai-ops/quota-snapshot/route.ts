import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * POST /api/ai-ops/quota-snapshot
 *
 * Record or update a quota reading for a provider.
 * Called by the confirmation UI and (eventually) the browser extension.
 *
 * Body: { provider, quota_remaining_pct, snapshot_source?, notes? }
 */
export async function POST(request: NextRequest) {
  let body: any
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'invalid json' }, { status: 400 })
  }

  const { provider, quota_remaining_pct, snapshot_source = 'user_confirmed', notes } = body

  if (!provider || typeof quota_remaining_pct !== 'number') {
    return Response.json({ error: 'provider and quota_remaining_pct are required' }, { status: 400 })
  }

  if (!['anthropic', 'openai', 'google'].includes(provider)) {
    return Response.json({ error: 'unknown provider' }, { status: 400 })
  }

  if (quota_remaining_pct < 0 || quota_remaining_pct > 100) {
    return Response.json({ error: 'quota_remaining_pct must be 0–100' }, { status: 400 })
  }

  const supabase = createServiceRoleClient()

  // Ensure a provider_account row exists (upsert with a sentinel company_id)
  // For single-user deployments we use a fixed company_id derived from the first company
  const { data: company } = await supabase
    .from('companies')
    .select('id')
    .limit(1)
    .single()

  if (!company) {
    return Response.json({ error: 'no company found' }, { status: 500 })
  }

  const { data: account, error: accountErr } = await supabase
    .from('provider_accounts')
    .upsert(
      { company_id: company.id, provider, account_type: 'subscription', updated_at: new Date().toISOString() },
      { onConflict: 'company_id,provider', ignoreDuplicates: false }
    )
    .select('id')
    .single()

  if (accountErr || !account) {
    return Response.json({ error: accountErr?.message ?? 'upsert failed' }, { status: 500 })
  }

  // Confidence based on source
  const confidence =
    snapshot_source === 'browser_extension' || snapshot_source === 'api' ? 'high'
    : snapshot_source === 'user_confirmed' ? 'high'
    : 'low'

  // Expire user-confirmed snapshots after 8 hours
  const expires_at = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()

  const { error: snapErr } = await supabase.from('provider_quota_snapshots').insert({
    provider_account_id: account.id,
    snapshot_source,
    quota_remaining_pct,
    confidence,
    notes: notes ?? null,
    expires_at,
  })

  if (snapErr) {
    return Response.json({ error: snapErr.message }, { status: 500 })
  }

  return Response.json({ ok: true })
}
