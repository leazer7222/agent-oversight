import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/**
 * POST /api/ai-ops/provider-account
 *
 * Upsert a provider account with reset schedule config.
 *
 * Body: { provider, quota_reset_period, quota_reset_anchor, plan_tier? }
 */
export async function POST(request: NextRequest) {
  let body: any
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'invalid json' }, { status: 400 })
  }

  const { provider, quota_reset_period, quota_reset_anchor, plan_tier } = body

  if (!provider || !['anthropic', 'openai', 'google'].includes(provider)) {
    return Response.json({ error: 'invalid provider' }, { status: 400 })
  }

  if (!['weekly', 'monthly'].includes(quota_reset_period)) {
    return Response.json({ error: 'quota_reset_period must be weekly or monthly' }, { status: 400 })
  }

  if (typeof quota_reset_anchor !== 'number') {
    return Response.json({ error: 'quota_reset_anchor is required' }, { status: 400 })
  }

  if (quota_reset_period === 'weekly' && (quota_reset_anchor < 0 || quota_reset_anchor > 6)) {
    return Response.json({ error: 'weekly anchor must be 0 (Sun) – 6 (Sat)' }, { status: 400 })
  }

  if (quota_reset_period === 'monthly' && (quota_reset_anchor < 1 || quota_reset_anchor > 31)) {
    return Response.json({ error: 'monthly anchor must be 1–31' }, { status: 400 })
  }

  const supabase = createServiceRoleClient()

  const { data: company } = await supabase
    .from('companies')
    .select('id')
    .limit(1)
    .single()

  if (!company) {
    return Response.json({ error: 'no company found' }, { status: 500 })
  }

  const { error } = await supabase
    .from('provider_accounts')
    .upsert(
      {
        company_id: company.id,
        provider,
        account_type: 'subscription',
        quota_reset_period,
        quota_reset_anchor,
        plan_tier: plan_tier ?? null,
        updated_at: new Date().toISOString(),
      },
      { onConflict: 'company_id,provider' }
    )

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  return Response.json({ ok: true })
}
