// Runtime Governance — Budget reservation and settlement helpers
// Phase 1 operating mode: data capture without enforcement.
// The SERIALIZABLE create_reservation function (RFC-004 §5) is deferred to Phase 3.
//
// RFC references: RFC-002 (ART-005, ART-006), RFC-004

import type { SupabaseClient } from '@supabase/supabase-js'

// ---------------------------------------------------------------------------
// Period key helpers
// ---------------------------------------------------------------------------

export function currentPeriodKey(): string {
  const d = new Date()
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}

// ---------------------------------------------------------------------------
// Ensure a budget period exists for this tenant.
// Creates one on first use with a generous Phase 1 budget ($9999/month).
// INSERT ... ON CONFLICT DO NOTHING — safe to call concurrently.
// Returns the budget period row.
// ---------------------------------------------------------------------------

export async function ensureBudgetPeriod(
  supabase:  SupabaseClient,
  tenantId:  string,
  periodKey: string,
): Promise<{ id: string; budget_usd: number; reserved_usd: number; consumed_usd: number } | null> {
  // Try to create; silently skip if already exists (23505)
  await supabase
    .schema('runtime_governance')
    .from('budget_periods')
    .insert({
      tenant_id:   tenantId,
      period_key:  periodKey,
      period_type: 'monthly',
      budget_usd:  9999.0000,
    }, { onConflict: 'tenant_id,period_key' })
    .select('id')
    .maybeSingle()
    // The above may fail with 42P10 if the unique index names differ from what
    // PostgREST expects — fall through to the SELECT below in that case.

  // Always re-read the row so we have current reserved/consumed values
  const { data, error } = await supabase
    .schema('runtime_governance')
    .from('budget_periods')
    .select('id, budget_usd, reserved_usd, consumed_usd')
    .eq('tenant_id', tenantId)
    .eq('period_key', periodKey)
    .is('cost_center_id', null)
    .single()

  if (error) {
    console.error('[budget] ensureBudgetPeriod failed:', error.message, { tenantId, periodKey })
    return null
  }
  return data as { id: string; budget_usd: number; reserved_usd: number; consumed_usd: number }
}

// ---------------------------------------------------------------------------
// Create a budget reservation for a run.
// Phase 1: no enforcement — always succeeds if budget_period exists.
// Uses p95 estimate as reserved_usd (RFC-004 §5 default tier).
// Returns the reservation id, or null if creation fails.
// ---------------------------------------------------------------------------

export async function createReservation(
  supabase: SupabaseClient,
  opts: {
    runId:            string
    tenantId:         string
    estimateId:       string
    recommendationId: string | null
    periodKey:        string
    reservedUsd:      number
    budgetAvailable:  number
  },
): Promise<string | null> {
  const expiresAt = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString()  // 2h from now

  const { data, error } = await supabase
    .schema('runtime_governance')
    .from('budget_reservations')
    .insert({
      run_id:                       opts.runId,
      tenant_id:                    opts.tenantId,
      estimate_id:                  opts.estimateId,
      recommendation_id:            opts.recommendationId,
      trace_id:                     opts.runId,   // Phase 1: trace_id = run_id (no multi-run traces)
      period_key:                   opts.periodKey,
      reserved_usd:                 opts.reservedUsd,
      reservation_tier:             'p95',
      hard_limit_usd:               null,
      soft_limit_usd:               null,
      budget_available_at_dispatch: opts.budgetAvailable,
      status:                       'active',
      expires_at:                   expiresAt,
    })
    .select('id')
    .single()

  if (error) {
    if (error.code !== '23505') {  // duplicate run_id is a benign retry
      console.error('[budget] createReservation failed:', error.message, { runId: opts.runId })
    }
    return null
  }

  // Phase 1: increment budget_period.reserved_usd (best-effort, not serializable).
  // Fetch current value then update — acceptable race risk for dark-launch data capture.
  // Phase 3 replaces this with the SERIALIZABLE create_reservation function (RFC-004 §5).
  const { data: period } = await supabase
    .schema('runtime_governance')
    .from('budget_periods')
    .select('id, reserved_usd, version')
    .eq('tenant_id', opts.tenantId)
    .eq('period_key', opts.periodKey)
    .is('cost_center_id', null)
    .single()

  if (period) {
    await supabase
      .schema('runtime_governance')
      .from('budget_periods')
      .update({
        reserved_usd: parseFloat(((period.reserved_usd as number) + opts.reservedUsd).toFixed(6)),
        updated_at:   new Date().toISOString(),
        version:      (period.version as number) + 1,
      })
      .eq('id', period.id)
  }

  return data.id as string
}

// ---------------------------------------------------------------------------
// Settle a reservation on run completion.
// Writes a settlement_record and updates the reservation status.
// Idempotent: duplicate settlement (23505) is silently ignored.
// ---------------------------------------------------------------------------

export async function settleReservation(
  supabase: SupabaseClient,
  opts: {
    runId:          string
    tenantId:       string
    actualCostUsd:  number
    isProvisional:  boolean
    source:         'telemetry' | 'estimated'
  },
): Promise<void> {
  // Find the reservation for this run
  const { data: reservation } = await supabase
    .schema('runtime_governance')
    .from('budget_reservations')
    .select('id, reserved_usd, period_key')
    .eq('run_id', opts.runId)
    .eq('status', 'active')
    .maybeSingle()

  if (!reservation) return   // no reservation to settle (pre-Group-4 run or already settled)

  const settlementType = opts.isProvisional ? 'provisional'
    : opts.actualCostUsd > (reservation.reserved_usd as number) ? 'overrun' : 'normal'

  // Write settlement record (append-only; 23505 = already settled)
  const { error: settlErr } = await supabase
    .schema('runtime_governance')
    .from('settlement_records')
    .insert({
      reservation_id:    reservation.id,
      tenant_id:         opts.tenantId,
      settlement_type:   settlementType,
      actual_cost_usd:   opts.actualCostUsd,
      settlement_source: opts.source,
      is_provisional:    opts.isProvisional,
    })

  if (settlErr && settlErr.code !== '23505') {
    console.error('[budget] settlement_records write failed:', settlErr.message, { runId: opts.runId })
    return
  }

  // Update reservation status (only mutable field — RFC-002 ART-005)
  await supabase
    .schema('runtime_governance')
    .from('budget_reservations')
    .update({
      status:     opts.isProvisional ? 'provisional_settlement' : 'settled',
      updated_at: new Date().toISOString(),
    })
    .eq('id', reservation.id)
    .eq('status', 'active')   // guard: only transition from active
}
