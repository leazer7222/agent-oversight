import { apiFetch } from '@/lib/api/fetch'
import { formatDateTime } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface InvariantReport {
  checked_at:                        string
  telemetry_events_5min:             number
  telemetry_events_1h:               number
  runs_awaiting_evaluation:          number
  runs_without_recommendation_24h:   number
  runs_without_estimate_24h:         number
  unsettled_reservations:            number
  estimates_missing_features:        number
  n_tup_upd_estimate_artifacts:      number
  n_tup_upd_evaluation_artifacts:    number
  n_tup_upd_recommendation_artifacts:number
  n_tup_upd_pricing_table_versions:  number
  n_tup_upd_task_types:              number
  n_tup_upd_raw_events:              number
  task_distribution_7d:              { code: string; label: string; count: number }[]
  complexity_distribution_7d:        { bucket: string; count: number }[]
  estimation_tier_breakdown:         { tier: string; count: number }[]
  accuracy_overview:                 {
    total_evaluations:      number
    complete_evaluations:   number
    incomplete_evaluations: number
    avg_pct_error:          number | null
    underestimated_pct:     number | null
  }
  totals: {
    runs_24h:                  number
    runs_7d:                   number
    estimate_artifacts:        number
    evaluation_artifacts:      number
    recommendation_artifacts:  number
    budget_reservations:       number
    raw_events_total:          number
  }
  error?: string
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

type Level = 'pass' | 'warn' | 'fail'

function status(value: number, warnAbove: number, failAbove: number): Level {
  if (value > failAbove)   return 'fail'
  if (value > warnAbove)   return 'warn'
  return 'pass'
}

const LEVEL_STYLES: Record<Level, string> = {
  pass: 'bg-emerald-950/40 border-emerald-900/60 text-emerald-400',
  warn: 'bg-amber-950/40  border-amber-900/60  text-amber-400',
  fail: 'bg-red-950/40    border-red-900/60    text-red-400',
}
const LEVEL_DOT: Record<Level, string> = {
  pass: 'bg-emerald-500',
  warn: 'bg-amber-500',
  fail: 'bg-red-500',
}
const LEVEL_LABEL: Record<Level, string> = { pass: 'PASS', warn: 'WARN', fail: 'FAIL' }

function Chip({ level, label, value }: { level: Level; label: string; value: string | number }) {
  return (
    <div className={`flex items-center justify-between gap-4 rounded-lg border px-4 py-3 ${LEVEL_STYLES[level]}`}>
      <div className="flex items-center gap-2.5 min-w-0">
        <span className={`h-2 w-2 rounded-full shrink-0 ${LEVEL_DOT[level]}`} />
        <span className="text-sm font-medium text-zinc-200 truncate">{label}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs font-mono text-zinc-400">{value}</span>
        <span className={`text-xs font-bold tracking-wide ${level === 'pass' ? 'text-emerald-500' : level === 'warn' ? 'text-amber-500' : 'text-red-500'}`}>
          {LEVEL_LABEL[level]}
        </span>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className="text-sm font-medium text-zinc-200">{value}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function InvariantsPage() {
  const report = await apiFetch<InvariantReport>('/api/monitoring/invariants')

  if (!report || report.error) {
    return (
      <div className="p-6 space-y-4 max-w-4xl">
        <h1 className="text-xl font-semibold text-zinc-100">Invariants</h1>
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">
          {report?.error ?? 'Failed to load report — migrations 013-020 may not yet be applied.'}
        </div>
      </div>
    )
  }

  const immutabilityViolations =
    (report.n_tup_upd_estimate_artifacts ?? 0) +
    (report.n_tup_upd_evaluation_artifacts ?? 0) +
    (report.n_tup_upd_recommendation_artifacts ?? 0) +
    (report.n_tup_upd_pricing_table_versions ?? 0) +
    (report.n_tup_upd_task_types ?? 0) +
    (report.n_tup_upd_raw_events ?? 0)

  const checks: { level: Level; label: string; value: string | number }[] = [
    {
      level: status(report.runs_awaiting_evaluation, 0, 0),
      label: 'Evaluation coverage — runs awaiting artifact > 10 min',
      value: report.runs_awaiting_evaluation,
    },
    {
      level: status(report.runs_without_estimate_24h, 2, 5),
      label: 'Estimate coverage — runs without estimate (24h)',
      value: report.runs_without_estimate_24h,
    },
    {
      level: status(report.runs_without_recommendation_24h, 2, 5),
      label: 'Recommendation coverage — runs without artifact (24h)',
      value: report.runs_without_recommendation_24h,
    },
    {
      level: status(report.unsettled_reservations, 0, 0),
      label: 'Budget — active reservations for completed runs > 15 min',
      value: report.unsettled_reservations,
    },
    {
      level: status(report.estimates_missing_features, 0, 0),
      label: 'Feature snapshot — estimates with NULL snapshot',
      value: report.estimates_missing_features,
    },
    {
      level: status(immutabilityViolations, 0, 0),
      label: 'Immutability — UPDATE count on Class I artifact tables',
      value: immutabilityViolations,
    },
  ]

  const overallLevel: Level = checks.some(c => c.level === 'fail') ? 'fail'
    : checks.some(c => c.level === 'warn') ? 'warn'
    : 'pass'

  const overallStyle = overallLevel === 'fail' ? 'border-red-800 bg-red-950/30 text-red-300'
    : overallLevel === 'warn' ? 'border-amber-800 bg-amber-950/30 text-amber-300'
    : 'border-emerald-800 bg-emerald-950/30 text-emerald-300'
  const overallText = overallLevel === 'fail' ? 'Invariant violation detected'
    : overallLevel === 'warn' ? 'Warning — some checks degraded'
    : 'All invariants passing'

  const tot = report.totals ?? {}
  const acc = report.accuracy_overview

  return (
    <div className="p-6 space-y-8 max-w-4xl">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Invariants</h1>
          <p className="text-sm text-zinc-500 mt-0.5">Phase 1 Class C monitoring — RFC-002, RFC-003, RFC-004, RFC-005, RFC-009</p>
        </div>
        <span className="text-xs text-zinc-600 mt-1 shrink-0">
          {report.checked_at ? `Checked ${formatDateTime(report.checked_at)}` : ''}
        </span>
      </div>

      {/* Overall status banner */}
      <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${overallStyle}`}>
        <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${
          overallLevel === 'fail' ? 'bg-red-500' : overallLevel === 'warn' ? 'bg-amber-500' : 'bg-emerald-500'
        }`} />
        <span className="text-sm font-semibold">{overallText}</span>
        <span className="text-xs opacity-60 ml-auto">
          {checks.filter(c => c.level === 'pass').length}/{checks.length} checks passing
        </span>
      </div>

      {/* Invariant checks */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Invariant checks</h2>
        <div className="space-y-1.5">
          {checks.map(c => (
            <Chip key={c.label} level={c.level} label={c.label} value={c.value} />
          ))}
        </div>
      </section>

      {/* Pipeline metrics */}
      <section className="space-y-3">
        <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Pipeline metrics</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Runs (24h)"            value={(tot.runs_24h ?? 0).toLocaleString()} />
          <Stat label="Runs (7d)"             value={(tot.runs_7d ?? 0).toLocaleString()} />
          <Stat label="Estimate artifacts"    value={(tot.estimate_artifacts ?? 0).toLocaleString()} />
          <Stat label="Evaluation artifacts"  value={(tot.evaluation_artifacts ?? 0).toLocaleString()} />
          <Stat label="Recommendations"       value={(tot.recommendation_artifacts ?? 0).toLocaleString()} />
          <Stat label="Reservations"          value={(tot.budget_reservations ?? 0).toLocaleString()} />
          <Stat label="Telemetry events (1h)" value={(report.telemetry_events_1h ?? 0).toLocaleString()} />
          <Stat label="Raw events total"      value={(tot.raw_events_total ?? 0).toLocaleString()} />
        </div>
      </section>

      {/* Estimation accuracy */}
      {acc && (acc.total_evaluations ?? 0) > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Estimation accuracy</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Evaluations total"   value={acc.total_evaluations} />
            <Stat label="Complete telemetry"  value={acc.complete_evaluations} />
            <Stat label="Avg error %"         value={acc.avg_pct_error != null ? `${acc.avg_pct_error}%` : '—'} />
            <Stat label="Underestimated"      value={acc.underestimated_pct != null ? `${acc.underestimated_pct}%` : '—'} />
          </div>
        </section>
      )}

      {/* Immutability detail */}
      <section className="space-y-3">
        <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Immutability (UPDATE counts since last DB restart)</h2>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 divide-y divide-zinc-800">
          {[
            ['estimate_artifacts',         report.n_tup_upd_estimate_artifacts],
            ['evaluation_artifacts',        report.n_tup_upd_evaluation_artifacts],
            ['recommendation_artifacts',    report.n_tup_upd_recommendation_artifacts],
            ['pricing_table_versions',      report.n_tup_upd_pricing_table_versions],
            ['task_types',                  report.n_tup_upd_task_types],
            ['raw_events',                  report.n_tup_upd_raw_events],
          ].map(([table, upd]) => (
            <div key={table as string} className="flex items-center justify-between px-4 py-2.5">
              <span className="text-xs font-mono text-zinc-400">{table as string}</span>
              <span className={`text-xs font-mono ${(upd as number) > 0 ? 'text-red-400 font-bold' : 'text-emerald-500'}`}>
                {(upd as number) > 0 ? `${upd} updates` : '0'}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Task distribution */}
      {(report.task_distribution_7d ?? []).length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Task distribution (7 days)</h2>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
            <div className="grid grid-cols-[1fr_auto_auto] gap-x-6 px-4 py-2 border-b border-zinc-800">
              <span className="text-xs text-zinc-500">Type</span>
              <span className="text-xs text-zinc-500 text-right">Runs</span>
              <span className="text-xs text-zinc-500 text-right w-20">Share</span>
            </div>
            {(() => {
              const total = report.task_distribution_7d.reduce((s, r) => s + r.count, 0)
              return report.task_distribution_7d.map(row => (
                <div key={row.code} className="grid grid-cols-[1fr_auto_auto] gap-x-6 px-4 py-2.5 border-b border-zinc-800/60 last:border-0">
                  <div>
                    <span className="text-sm text-zinc-200">{row.label}</span>
                    <span className="text-xs text-zinc-600 ml-2 font-mono">{row.code}</span>
                  </div>
                  <span className="text-sm text-zinc-300 text-right">{row.count.toLocaleString()}</span>
                  <div className="w-20 flex items-center justify-end gap-2">
                    <span className="text-xs text-zinc-500">{total > 0 ? `${((row.count / total) * 100).toFixed(0)}%` : '—'}</span>
                  </div>
                </div>
              ))
            })()}
          </div>
        </section>
      )}

      {/* Complexity + estimation tier side by side */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        {(report.complexity_distribution_7d ?? []).length > 0 && (
          <section className="space-y-3">
            <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Complexity (7 days)</h2>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 divide-y divide-zinc-800">
              {report.complexity_distribution_7d.map(row => (
                <div key={row.bucket} className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-sm text-zinc-300 capitalize">{row.bucket}</span>
                  <span className="text-sm font-mono text-zinc-400">{row.count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {(report.estimation_tier_breakdown ?? []).length > 0 && (
          <section className="space-y-3">
            <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Estimation tier</h2>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 divide-y divide-zinc-800">
              {report.estimation_tier_breakdown.map(row => (
                <div key={row.tier} className="flex items-center justify-between px-4 py-2.5">
                  <span className={`text-sm ${
                    row.tier === 'calibrated'         ? 'text-emerald-400'
                    : row.tier === 'deterministic'     ? 'text-zinc-300'
                    : row.tier === 'embedded_fallback' ? 'text-amber-400'
                    : 'text-zinc-400'
                  }`}>{row.tier}</span>
                  <span className="text-sm font-mono text-zinc-400">{row.count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

    </div>
  )
}
